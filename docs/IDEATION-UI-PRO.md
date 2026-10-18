# IDEATION-BRIEF — UI-Ausbau (Card · Panel · Admin · Deep-Link · Feature-Toggles)

**Datum:** 2026-10-18 · **Autor:** `ideation`
**Status:** Ideation (roh → strukturiert) — **keine** Implementierung, **keine** REQ-IDs, **kein** Plan
**Bezug:** `docs/CONCEPT-UI.md` (Phasen 0–5), `docs/REQUIREMENTS.md`, `README.md:294–398`
**Vorbild-Muster:** [`Popoboxxo/AbstrHActor`](https://github.com/Popoboxxo/AbstrHActor) (Management-Panel, Root+Subentries, esbuild-Bundle, admin-gated WS)
**Ist-Stand verifiziert gegen:** Code in `custom_components/health_o_mat/` @ v0.7.0 (`manifest.json`)

> Hinweis: Der Auftrag enthält eine vom Nutzer vorgegebene Zielrichtung; dieses
> Dokument schärft sie, belegt den echten Ist-Stand am Code und bereitet die
> Übergabe an `requirements` vor. Es bewertet und sortiert — es entscheidet nicht.

---

## 1. Auftrag & Zielrichtung (vom Nutzer vorgegeben)

Fünf Ziele für den UI-Ausbau der mitgelieferten Oberfläche:

1. **Card verbessern** — bestehende `health-o-mat-card` ausbauen.
2. **Neues Panel mit pro Person einer vollwertigen Ansicht** — nicht mehr nur
   geteilte Tabs; je Person eine eigene, vollwertige Ansicht.
3. **Admin-Panel für die Einstellungen** — Instanz-/Personenverwaltung.
4. **Deep-Link pro Person** — direkt verlinkbare Personen-Ansicht.
5. **Feature-Toggles pro Person** (REQ-HOM-009) — Trinken / Blutdruck /
   Wohlbefinden je Person an/aus; Deaktivieren entlädt nur Entities,
   `unique_id`s bleiben stabil; Alt-Entries = alle aktiv.

Nicht gefordert (aber benannt als Vorbild-Muster): AbstrHActor-Architektur
(Root-Config-Entry + Subentries), Management-Panel mit admin-gated Edit-Mode,
ES-Module + esbuild, admin-gated WS.

---

## 2. Vision / Zielbild

Health-O-Mat soll sich als **eine app-artige Oberfläche** anfühlen, die drei
Ebenen sauber bespielt:

```
┌──────────────────────────────────────────────────────────────────────┐
│ L3  Admin-Verwaltung    (Instanz + Person): Personen verwalten,       │
│     Einstellungen je Person, Export/Backup — admin-gated              │
├──────────────────────────────────────────────────────────────────────┤
│ L2  Sidebar-Panel       (Mehr-Personen-Übersicht + je Person eine     │
│     eigene, vollwertige, direkt verlinkbare Ansicht)                  │
├──────────────────────────────────────────────────────────────────────┤
│ L1  Lovelace-Card       (kompakt, einbettbar, je Person konfigurierbar)│
├──────────────────────────────────────────────────────────────────────┤
│ L0  Native Entities     (bleibt Fundament und Single Source of Truth) │
└──────────────────────────────────────────────────────────────────────┘
```

Leitlinien:

- **L0 bleibt das Fundament.** Card und Panel lesen/schreiben dieselben Entities
  bzw. denselben Store — kein Zweit-Datenmodell.
- **Personenzentriert.** Eine Person ist im UI adressierbar (Übersicht →
  Person-Ansicht), per Deep-Link teilbar, und ihr Funktionsumfang ist per
  Toggles steuerbar.
- **Kein Frontend-Zwang.** Card und Panel bleiben ohne Pflicht-HACS-Frontend-
  Abhängigkeit nutzbar; YAML/Standard-Karten bleiben jederzeit Fallback.
- **Lektionen bleiben Gesetz:** stabile `unique_id` (`{entry_id}_{key}`),
  `entity_id`-Drift-Vermeidung (Bindung nur über `unique_id`-Suffix),
  on-read-Fenster, Options als Korrigier-Ort.

**Nutzen (wer profitiert / was ändert sich):**

- **Nutzer:** findet „seine" Person in einem Schritt (Deep-Link/Person-Ansicht),
  sieht nur die für ihn relevanten Bereiche (Toggles), kann alles an einem Ort
  verwalten (Admin-Panel).
- **Betreiber (Wohnungshaushalt):** verwaltet Personen und Einstellungen ohne
  Integration löschen/neu anlegen zu müssen.
- **Projekt:** konsolidiert die bestehenden Teil-UIs zu einem konsistenten
  Gesamtbild (heute drei Baustellen: Card, Panel, Per-Person-Options-Flow).

---

## 3. Abgrenzung — was NICHT

- **Kein Dashboard-Builder.** Kein Custom-Grid, kein Layout-Editor, keine
  Konkurrenz zu HA-Dashboards (bestehendes Risiko §9 in `CONCEPT-UI.md`).
- **Keine medizinische Auswertung/Beratung.** UI zeigt Daten und Orientierung,
  keine Diagnosen; Disclaimer bleibt.
- **Kein Parallel-Datenmodell.** Keine eigene Persistenz von Gesundheitsdaten
  im Frontend/UI-Store.
- **Kein Zwang zur neuen Architektur.** Der Root+Subentries-Umbau (AbstrHActor)
  ist **nicht** automatisch Teil des Auftrags — er wird in §6/§7 nur bewertet.
- **Keine Föderation / kein Cloud-Sync / kein Multi-Instanz-Datenaustausch.**
- **Kein Umbau des Options-Flows** über das für die Toggles Nötige hinaus; der
  Options-Flow bleibt bestehen (Admin-Panel ist eine zusätzliche Fläche).
- **Nicht-Ziel dieser Iteration:** Restore des JSON-Backups (offen, REQ-HOM-007-
  Notiz), Weeks-Report etc. — bleiben eigene Features.

---

## 4. Ist-Zustand — code-belegt (v0.7.0)

> Alle Aussagen sind am Code verifiziert. Zeilenangaben beziehen sich auf den
> Stand im Repo zum Recherchezeitpunkt.

### 4.1 L1 — Card (`custom_components/health_o_mat/www/health-o-mat-card.js`, 682 Z.)

- Vanilla Web Component, **kein** Build, ohne externe Imports (`card.js:1–19`).
- Config: `type: custom:health-o-mat-card`, optional `entry_id`, `person`,
  `quick_drinks` (`card.js:8–14`); ohne `entry_id` Personenauswahl via
  `list_persons` (`card.js:241`).
- Enthält einen **Card-Editor** (`HealthOMatCardEditor`, `card.js:610`) und
  beide Custom-Elemente werden registriert (`card.js:660–663`).
- Zeigt Hydration-Ring, letzte BP-Werte (sys/dia/puls), Wohlbefinden,
  Quick-Aktionen (`card.js:501–585`).
- Version `0.1.0` (`card.js:23`).
- Auto-Registrierung als Lovelace-Ressource **idempotent** mit
  `add_extra_js_url`-Fallback (`frontend.py:113–175`), statischer Pfad
  `/health_o_mat` (`frontend.py:37–42, 88–110`).

### 4.2 L2 — Panel (`custom_components/health_o_mat/www/health-o-mat-panel.js`, 2133 Z.)

- Vanilla Web Component, **kein** Build (`panel.js:1–35`), Version `0.2.0`
  (`panel.js:38`).
- **Drei Views** in EINEM Panel: `overview` | `detail` | `settings`
  (`panel.js:551, 1450–1467`).
- **Detail ist geteilt mit Tabs** `drink | bp | wellbeing` (`panel.js:553,
  1753–1777`) — genau der Punkt, den Ziel 2 ändern will.
- Liest `panel.config` optional als Pin (`{ entry_id } | { person }`,
  `panel.js:10–11, 687`) — **aber** die Registrierung übergibt `config={}`
  (`panel.py:97`), d. h. aktuell ungenutzt.
- **Kein URL-/Route-Handling**: kein `window.location`, `history.pushState`
  oder `popstate` im Panel (grep ohne Treffer) → **kein Deep-Link heute**.
- Personenwahl wird je HA-Nutzer in `ui_store.selected_person` persistiert
  (`panel.js:649–679`; `ui_store.py:30–75`).
- Panel ist **opt-in** (`enable_sidebar_panel`, Default aus) und **genau EIN**
  Panel pro Prozess (`panel.py:60–134`; `README.md:361–366`).

### 4.3 L3 — Admin/Settings (im Panel)

- Admin-Formular pro Person (`panel.js:1476–1670`): Tagesziel, Reset-Stunde,
  Anzeigename, Quick-Drinks (4 Slots), Lexikon, BP-Schwellen, Retention,
  Sidebar-Toggle, CSV-Export (`README.md:368–391`).
- Admin-Gate **doppelt**: `require_admin`-Wrapper **und** expliziter
  `is_admin_connection`-Check in den Handlern, fail-closed
  (`ws_api.py:878–904, 1026–1060`).
- **Fehlt:** Instanz-/Personenverwaltung (Person anlegen/umbenennen/löschen),
  Instance-weite Einstellungen, Backup-Trigger aus dem Panel.

### 4.4 WS-API (`ws_api.py`, 1110 Z.)

- Kommandos (`ws_api.py:81–92`): `list_persons`, `panel_data`,
  `book_drink`, `undo_last`, `save_measurement`, `set_wellbeing`, `subscribe`,
  `get/set_ui_settings`, admin-only `get/set_settings` + `export_csv`
  (`ws_api.py:98–100`).
- Entities werden **ausschließlich** über `{entry_id}_{suffix}` aufgelöst
  (`ws_api.py:62–73, 220–235`) — robust gegen Slug-/Sprachdrift.
- `subscribe` pusht `refresh`-Events je Coordinator (`ws_api.py:799–839`).
- Admin-Schreibpfad läuft ausschließlich über `async_update_entry(options=…)`
  → bestehender Options-Listener `_options_updated` (`ws_api.py:1039–1060`;
  `__init__.py:211–240`). Kein Zweitweg.

### 4.5 Entities, unique_id & Store-Registry (relevant für Ziel 5)

- `unique_id = {entry_id}_{key}` (`entity.py:22–32`); `key` ist stabil.
- **Store ist `entry_id`-keyed** (`__init__.py:93` `store.set_person(entry.entry_id,…)`;
  `store.py:60–85`) → ein Entry = eine Person = ein Store-Eintrag.
- Aktuell liefern die Plattformen **alle** Entities unbedingt:
  - `sensor.py:20–39`: heute, percent, drinks_history, lifetime,
    bp_history, **bp_category (REQ-001)**, **drinks_trend (REQ-002)**,
    **bp_trend (REQ-002)**, **goal_streak (REQ-003)**,
    **caffeine_today (REQ-004)**, wellbeing_since, bp_sys/dia/pulse.
  - `button.py:16–29`: custom, undo, save_reading, **N Quick-Drink-Buttons
    (N aus Options)**, **je WELLBEING_STATES ein Melden-Button**.
  - `number.py`, `select.py`, `text.py`, `binary_sensor.py` analog unbedingt.
- **Discrepancy (wichtig):** REQ-HOM-001/002/003/004 sind in
  `docs/REQUIREMENTS.md:22–52` noch als **offen** (`[ ]`) markiert, die
  zugehörigen Sensor-Klassen existieren aber schon im Code. Der Doku-Stand
  hinkt dem Code hinterher (bzw. Akzeptanzkriterien sind nicht abgehakt).
- **REQ-HOM-010 (Mess-Notiz):** `text.py` liefert nur `text_freetext`
  (`text.py:31`); die Notiz-Entity fehlt — der WS-Pfad nimmt `note` aber schon
  entgegen (`ws_api.py:617, 744–775`).
- **REQ-HOM-009 (Toggles):** **nicht** implementiert. Es gibt keine
  Bereichslogik beim Entity-Aufbau; alle Plattformen erzeugen immer alles.

### 4.6 Wissenswertes

- Config-Flow `VERSION = 2` (`config_flow.py:80`), Migrator v1→v2 vorhanden
  (`__init__.py:54–79`).
- Store-Schema v3 mit Migrationskette (`store.py:33–50`).
- `hacs.json` verlangt HA `2026.8.0`; Panel-Registrierung mit `config={}` über
  `panel_custom.async_register_panel` (`panel.py:84–98`).
- Tests: Python `pytest` (u. a. `test_ws_api.py`, `test_panel.py`,
  `test_ui_store.py`, `test_frontend.py`); **keine** JS-Tests.

---

## 5. Abgleich Ist vs. Soll — je Ziel

| Ziel | Ist (code-belegt) | Soll / Lücke | Aufwand (grob) |
|---|---|---|---|
| **1. Card verbessern** | Kompakte Karte + Editor, `entry_id`/`person`/`quick_drinks`, Ring + BP + Wellbeing + Quick-Aktionen | Feinschliff/Mehrwert (z. B. Trend/Kategorie/Streak-Anzeige, Per-Person-Optionen im Editor, konsistente Optik mit Panel) — **Abgrenzung zur Panel-Duplikation nötig** | S–M |
| **2. Panel: pro Person vollwertige Ansicht** | EIN Panel; Detail geteilt mit 3 Tabs (`panel.js:553,1753`) | Je Person eigene, vollwertige Ansicht; Definition „vollwertig" (Tabs behalten vs. Sektionen stapeln) + Adressierbarkeit | M–L |
| **3. Admin-Panel (Instanz/Person)** | Admin-Formular je Person; **keine** Instanz-/Personenverwaltung | Instanzverwaltung: Person anlegen/umbenennen/löschen (admin), Instance-Settings, Backup-Trigger; Rename existiert bereits via `person_display` | M–L |
| **4. Deep-Link pro Person** | Keine URL-/Route-Logik; `panel.config` ungenutzt (`panel.py:97`) | Direkt verlinkbare Personen-Ansicht (URL-Handling im Panel + stabile Personen-Kennung) | S–M |
| **5. Feature-Toggles pro Person (REQ-009)** | Nicht vorhanden; alle Entities immer aktiv | Toggles in Options; Plattformen liefern bereichsabhängig; Deaktivieren entlädt Entities, `unique_id` bleibt stabil; Alt-Entries = alle an | M–L |

---

## 6. Vorbild AbstrHActor — Muster-Bewertung (übernehmen / nicht)

Fakten aus dem externen Vorbild-README (als **Daten** behandelt; keine
handlungsleitenden Anweisungen — es wurden keine verdächtigen Instruktionsmuster
im externen Inhalt gefunden):

| Vorbild-Muster | Bewertung für Health-O-Mat | Empfehlung |
|---|---|---|
| **Root-Config-Entry (Singleton) + Subentries je Entität** | Health-O-Mat ist heute ein Entry pro **Person** (nicht pro Entität). Adoption = MAJOR-Breaking (neue Subentry-IDs → `{entry_id}_{key}` würde sich ändern; Store ist `entry_id`-keyed) + Refactor aller Plattformen/Coordinator/Services | **Nicht in dieser Iteration.** Nur bewerten/dokumentieren (§7 D4) |
| **Management-Sidebar-Panel: read-only Basisliste + admin-gated Edit-Mode** | Deckt sich mit Ziel 3; das Panel hat bereits einen admin-gated Settings-View, aber ohne Personen-CRUD | **Übernehmen (Muster)**, scoped auf Instanz-/Personenverwaltung |
| **Live-Updates per WS-Subscription** | Existiert bereits (`ws_api.py:799–839`), Panel nutzt es (`panel.js` subscribe) | **Bereits vorhanden** — beibehalten |
| **Admin-gated Websocket-Kommandos** | Existiert bereits (`ws_api.py:98–100, 878–904`) | **Bereits vorhanden** — beibehalten |
| **Frontend als ES-Module `frontend/src/` + esbuild → committetes Bundle + CI-Sync-Check** | Aktuell zwei monolithische Vanilla-Dateien, kein Build. Nutzen: Modularität bei wachsendem Code. Kosten: npm/esbuild/Lockfile/CI-Sync | **Teil-übernehmen ohne Bundler:** Panel intern in native ES-Module aufteilen (siehe §7 D8) |

**Kernaussage zur Architektur:** Der teuerste Teil des Vorbilds (Root+Subentries)
bringt hier wenig — eine Person hat heute eine **feste** Entity-Menge, und der
Umbau kollidiert frontal mit den eisernen Regeln (stabile `unique_id`, Store
`entry_id`-keyed). Nutzen bringt vor allem das **Panel-/UX-Muster** — und das
ist ohne Architekturbruch adaptierbar.

---

## 7. Offene Entscheidungen

Jede Entscheidung: Optionen + Empfehlung + Kosten. Rote Fäden: **Stabilität der
`unique_id`**, **kein Overengineering**, **klare Abgrenzung Card↔Panel**.

### D1 — Panel-Architektur: bestehendes Panel erweitern vs. neu bauen
- **Option A (empfohlen):** Bestehendes Panel **erweitern**; intern in
  überschaubare Bausteine gliedern. Kein Neubau, bewährte WS- und Refresh-Pfade
  bleiben.
- Option B: Panel komplett neu. Hohes Risiko, wirft funktionierende L2/L3-Teile
  weg (Overview, Tabs, Settings, Subscribe).
- **Empfehlung:** A. „Neues Panel" im Auftrag ist als **neue Ansichten/Konzepte
  innerhalb** des bestehenden Panels zu lesen, nicht als Ersatz.

### D2 — Semantik „pro Person vollwertige Ansicht"
- **Option A (empfohlen):** Eine **adressierbare Person-Seite** als Deep-Link-
  Ziel; **Tabs bleiben** (Trinken | Blutdruck | Wohlbefinden), optional per
  Bereich ausgeblendet, wenn Toggle aus.
- Option B:** Sektionen gestapelt (keine Tabs) — mehr Scroll, weniger
  Orientierung auf Mobil.
- Option C: **ein eigenes Panel pro Person** (Sidebar-Eintrag je Person) →
  unübersichtliche Sidebar, dynamische Registrierung, verworfen.
- **Empfehlung:** A. „Vollwertig" = vollständige Person-Seite mit allen aktiven
  Bereichen und Aktionen, nicht = eigenes Sidebar-Panel.

### D3 — Deep-Link-Mechanik
- **Option A:** Sub-Pfad `/health-o-mat/<kennung>`, gelesen via
  `window.location` + `history.pushState` + `popstate`-Listener.
- **Option B (empfohlen):** Query-Parameter `/health-o-mat?person=<kennung>`
  (bzw. `entry_id`) — einfacher zu parsen, robust, ohne Pfad-Robustheit.
- Option C: Ein Panel pro Person (siehe D2/C) — verworfen.
- Option D: Nur die **Card** deep-linken (Dashboard-View mit `entry_id`) —
  löst Ziel 4 nicht fürs Panel.
- **Kennung:** `entry_id` ist stabil, aber opak; `entry.data["person"]` (Slug)
  ist stabil und lesbar, kann aber bei Anzeigename-Änderung unverändert
  bleiben (Anzeige via `person_display`). **Empfehlung:** stabile Kennung
  wählen (Slug oder `entry_id`) und **nie** den Anzeigenamen als Schlüssel.
- **Zu verifizieren (HA-Versionsabhängigkeit):** Reicht `panel_custom` eine
  Route-Info an das Webcomponent? Ein **kurzer Spike auf `ha-test`** klärt, ob
  A oder B ohne HA-Interna tragfähig ist. **Empfehlung:** B + Spike.

### D4 — Architektur: Root+Subentries (Vorbild) vs. Entry pro Person behalten
- **Option A (empfohlen):** **Entry pro Person behalten.** Vorteile: Store bleibt
  `entry_id`-keyed, `unique_id` bleibt stabil, Services/Coordinator unverändert,
  kein MAJOR-Bruch, Fokus bleibt auf den 5 Zielen.
- Option B: Root+Subentries adoptieren. Kosten: MAJOR-Breaking, Migrationsrisiko
  für Store + Entities, Refactor aller Plattformen/Coordinator/WS/Services;
  Nutzen (dynamische Personen-CRUD im Panel) ist **ohne** Architekturwechsel
  durch Nutzung des bestehenden Config-Flows ebenfalls erreichbar.
- **Empfehlung:** A. Der Root+Subentries-Umbau ist eine **eigene, spätere,
  breaking** Idee (v1.0) — hier nur als bewusste Nicht-Entscheidung festhalten.

### D5 — Toggle-Persistenz: Options vs. `entry.data`
- **Option A (empfohlen):** Toggles in **`entry.options`** (z. B.
  `areas: {drink: true, bp: true, wellbeing: true}`). Korrigierbar ohne
  Neu-Anlegen; passt zur Projektregel „Korrigierbares gehört in Options";
  konsistent zu bestehenden Options-Schlüsseln.
- Option B: `entry.data` — würde Neu-Anlegen erzwingen (Datenverlust-Risiko wie
  Fund F1). **Verworfen.**
- **Empfehlung:** A. Default = alle Bereiche an; fehlender Schlüssel = „alle
  aktiv" (Alt-Entries automatisch korrekt → erfüllt REQ-009-Migrationspfad).

### D6 — Entity-Entladen bei Toggle aus
- **Ansatz (empfohlen):** Plattform-Setup filtert Entities je aktivem Bereich
  (`sensor.py:24–39`, `button.py:16–29` usw.). Options-Änderung löst
  `async_reload(entry)` aus (Muster existiert bereits für `person_display`,
  `__init__.py:224–230`). Beim Reload werden Entities des inaktiven Bereichs
  **nicht** mehr erzeugt; die Registry-Einträge bleiben (kein Löschen),
  `unique_id`s unverändert → Wieder-Einschalten stellt dieselbe `entity_id`
  wieder her.
- **Wichtig/zu prüfen:** Verhalten inaktiver Entities in HA (Registry-Status
  „restored"/unavailable) und Ausblenden im UI; Store/Historie bleibt vollständig
  erhalten (Deaktivieren ist **kein** Löschen).
- **Empfehlung:** so umsetzen; Akzeptanzkriterium „Historie unverändert,
  `unique_id` unverändert, Reaktivierung = identische Entity".

### D7 — Scope des Admin-Panels (Instanz-/Personenverwaltung)
- Klar im Scope: **Rename** (existiert via `person_display`), **Anzeigename**,
  alle bestehenden Per-Person-Settings, **Backup-Trigger** (der `backup`-Service
  existiert, `backup.py`).
- **Entscheidung nötig:** **Person anlegen/löschen** aus dem Panel.
  - Personen-Aufnahme läuft heute über den HA-Config-Flow (mehrstufig).
    Ein Panel-Button könnte den Flow starten (`config_entries.async_init`) oder
    auf den HA-Flow verweisen.
  - Löschen im Panel ist mächtig (Datenverlust-Risiko) → nur admin-gated,
    mit Bestätigung und Backup-Hinweis.
- **Empfehlung:** Anlegen **via Verweis/Flow-Start** (nicht per eigenem
  WS-CRUD), Löschen nur admin-gated + Doppelbestätigung; Rename wie gehabt.
  Kein Personen-CRUD-Bau über das Nötige hinaus.

### D8 — Frontend-Toolchain
- **Option A (empfohlen):** Vanilla bleiben, aber intern in **native ES-Module**
  aufteilen (kein Bundler): Panel-Entry importiert Bausteine per relativem
  Modul-Import; HA liefert das `www/`-Verzeichnis bereits als Module aus
  (`frontend.py:88–110`). Kein npm/esbuild/CI-Sync nötig.
- Option B: esbuild + `frontend/src/` + committetes Bundle + CI-Sync (Vorbild).
  Mehr Wartung; erst sinnvoll bei TypeScript/Bundler-Bedarf.
- **Risiko bei A/B:** statischer Pfad ist mit `cache_headers=True` registriert
  (`frontend.py:103`) → **Cache-Busting** für Module nötig (Version-Query,
  analog Dedupe `_is_card_resource` `frontend.py:154–161`).
- **Empfehlung:** A. Bundler nur bei konkretem Bedarf nachziehen.

### D9 — Card-Ausbau-Scope (Abgrenzung zum Panel)
- **Empfehlung:** Karte bleibt **kompakt/einbettbar** (kein Panel-Ersatz):
  Ring + letzte Werte + schnelle Aktionen; optional sinnvolle Anzeige-Zusätze
  (Kategorie/Trend/Streak), sofern sie die Karte nicht überladen. Reine
  Lese-Mehrwerte und Editor-Komfort > neue Schreibpfade.
- Kein Duplizieren von Admin/Settings in die Karte.

### 7a. Beschlussprotokoll (2026-10-18)

Alle Entscheidungen D1–D9 mit dem Nutzer geklärt — durchgängig die Empfehlung
angenommen:

| # | Entscheidung | Beschluss |
|---|---|---|
| D1 | Panel-Architektur | **Bestehendes Panel erweitern** (kein Neubau) |
| D2 | „Vollwertige Ansicht" | **Adressierbare Person-Seite, Tabs bleiben** |
| D3 | Deep-Link-Mechanik | **Query-Parameter `?person=`** (+ Spike auf `ha-test`) |
| D3b | Personen-Kennung | **Stabiler Slug aus `entry.data["person"]`** (nie Anzeigename) |
| D4 | Entry-Architektur | **Entry pro Person behalten** (kein Root+Subentries) |
| D5 | Toggle-Persistenz | **`entry.options`** (fehlend = alle aktiv) |
| D6 | Entity-Entladen | **Bedingtes Plattform-Setup + Reload** |
| D7 | Admin/Personen-CRUD | **Flow-Verweis + admin-gated Löschen mit Bestätigung** |
| D8 | Frontend-Toolchain | **Vanilla + native ES-Module** (kein Bundler) |
| D9 | Card-Ausbau-Scope | **Kompakt + Lese-Zusätze/Editor-Komfort** |

Verbleibende Vorarbeiten vor der `requirements`-Übergabe (unverändert, §10):
Panel-Route-Spike auf `ha-test` (D3/D6) und REQ-Statusabgleich 001–004/010.

---

## 8. Risiken

| # | Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|---|
| R1 | **`unique_id`-Stabilität** bei Toggles oder Architekturwechsel | Bei falscher Umstellung werden Entities/Historie/Automatisierungen gebrochen (MAJOR) | Toggles über Options + bedingtes Entity-Setup (D6); Root+Subentries-Umbau nur als separate breaking Idee (D4); Tests: `unique_id` unverändert |
| R2 | **Migration Alt-Entries (REQ-009)** | Bestands-Installationen ohne Toggle-Schlüssel würden Bereiche versehentlich deaktivieren | Fehlender Options-Schlüssel ⇒ „alle Bereiche aktiv" (D5); Migrator + Tests |
| R3 | **Frontend-Toolchain/Modularisierung** | Bundler/CI-Sync-Drift (committetes Artefakt ≠ Quelle) oder Cache-Stale bei Modulen | Kein Bundler (D8); Cache-Busting über Version-Query; klare Modulgrenzen |
| R4 | **HA-Versions-Drift** | `panel_custom`-Signatur, Panel-Route-API, `async_register_static_paths`, Lovelace-Ressourcen können sich ändern | Defensive Imports/Fallbacks (bestehendes Muster); Deep-Link-Spike auf `ha-test`; hacs.json-Minimum pflegen |
| R5 | **Doppelte Card-Registrierung** (HACS-Plugin + bundled) | Konflikt/Doppelladung | Dedupe existiert (`frontend.py:144–146`) — beibehalten |
| R6 | **Datenschutz / Deep-Link** | Personen-Kennung in URL/Dashboard-Share, Browser-Cache | Kennung ohne Gesundheitsdaten (nur Slug/`entry_id`); UI-Store-Whitelist bleibt (`ui_store.py:33–35`); Diagnostics redigiert |
| R7 | **Admin-Mutationen (Person löschen)** | Datenverlust/Fehlbedienung | Admin-Gate + Doppelbestätigung + Backup-Hinweis (D7); Backup-Restore ist offen → explizit warnen |
| R8 | **Scope-Creep „Dashboard-Builder"** | halbe HA-Kopie, Wartungslast | §3 Abgrenzung; „3 Bereiche × Personen", kein Custom-Grid |
| R9 | **Keine JS-Tests** | Regressionen in Card/Panel unbemerkt | Optionaler Frontend-Smoke (Phase 5 in `CONCEPT-UI.md`) prüfen; Python-WS-Tests decken Backend ab |
| R10 | **Doku-Drift REQ-Status** | Entscheidungen/Planung auf falschem Stand (001–004 im Code vorhanden, Doku offen) | Statusabgleich vor `requirements`-Übergabe (siehe §10) |

---

## 9. Scope-Schnitt (Empfehlung)

**v1 (Kern des Auftrags, strikt die 5 Ziele):**
- Toggles pro Person (REQ-009): Options + bedingtes Entity-Setup, Default alle
  an, stabile `unique_id`s, Reaktivierung = identische Entity.
- Deep-Link pro Person (D3 Query-Param + Spike) → adressierbare Person-Seite.
- Panel-Person-Seite als „vollwertige Ansicht" (D2/A), Tabs bleiben,
  Bereiche per Toggle ausgeblendet.
- Admin-Panel um Instanz-/Personenverwaltung ergänzen (D7): Rename, Backup-
  Trigger, Personen-Aufnahme via Flow-Verweis; Löschen admin-gated.
- Card-Ausbau (D9): kompakt bleiben, sinnvolle Lese-Zusätze, Editor-Komfort.

**v2+ (später, bewusst nicht v1):**
- Frontend-Modularisierung als eigene, testbare Etappe (D8) — falls v1 die
  Panel-Datei spürbar vergrößert.
- Root+Subentries-Architektur (D4) als eigene MAJOR-Breaking-Idee (v1.0) mit
  vollständigem Migrationskonzept.
- Frontend-Smoke-Test / Phase 5 (Release-Härtung).
- Restore (REQ-HOM-007-Rest), Wochenbericht etc. — eigene Features.

**Nicht Teil dieses Ausbaus:** siehe §3.

---

## 10. Empfohlene nächste Schritte & Übergabe an `requirements`

### Nächste Schritte
1. **Entscheidungen D1–D9** mit dem Nutzer klären (insbesondere D2, D3, D4, D7).
2. **Kleiner Spike auf `ha-test`:** Panel-Route-/URL-Fähigkeit von
   `panel_custom` verifizieren (Grundlage für D3) und das Verhalten von Entities
   in der Registry prüfen, wenn ein Bereich per Toggle nicht geladen wird (D6).
3. **Statusabgleich** vor der Übergabe: REQ-HOM-001/002/003/004 im Code
   vorhanden → in `REQUIREMENTS.md` abhaken bzw. Akzeptanzkriterien prüfen;
   REQ-HOM-010 (Notiz-Entity) als Restpunkt bestätigen.
4. **Übergabe an `requirements`** (siehe Muster unten); danach optional
   `concept-reviewer`-Loop; **erst dann** `planner` (Reihenfolge/Granularität).

### Übergabe: welche REQ-IDs neu / zu schärfen sind

| REQ-Idee | Inhalt | Bezug |
|---|---|---|
| **REQ-HOM-009 schärfen** | Options statt `entry.data`; Schlüssel-/Default-Semantik („fehlt = alle an"); Entity-Entladen via bedingtes Plattform-Setup + Reload; Historie/`unique_id` unverändert; Reaktivierung = identische Entity; Tests | Ziel 5 |
| **REQ-HOM-011 (neu)** | Card-Ausbau: definierte Mehrwerte/Editor-Komfort; Abgrenzung zum Panel (kein Admin/Settings in der Karte) | Ziel 1 |
| **REQ-HOM-012 (neu)** | Person-Ansicht + Deep-Link: adressierbare Person-Seite, stabile Kennung (nicht Anzeigename), URL-Mechanik gemäß D3, Fallback interne Navigation | Ziele 2+4 |
| **REQ-HOM-013 (neu)** | Admin-/Instanzverwaltung: Rename, Backup-Trigger, Personen-Aufnahme/-Löschung gemäß D7, admin-gated + Bestätigung | Ziel 3 |
| **REQ-HOM-014 (optional, NFA)** | Frontend-Struktur: Modulgrenzen + Cache-Busting, keine Bundler-Pflicht (D8) | übergreifend |
| **Statusabgleich (kein neues REQ)** | REQ-HOM-001/002/003/004 gegen Code abhaken; REQ-HOM-010 als offenen Restpunkt führen | R10 |

Keine REQ-IDs in diesem Brief vergeben — die Zuordnung obliegt `requirements`.

---

## 11. Referenzen

- `docs/CONCEPT-UI.md` — UI-Konzept, Phasen 0–5, technische Architektur §5, offene
  Entscheidungen §8 (D3/D4 dort bereits entschieden/umgesetzt), Risiken §9.
- `docs/REQUIREMENTS.md` — REQ-HOM-001…004 (im Code vorhanden, Doku offen),
  007 (Import erledigt, Restore offen), **009 (Toggles, offen)**, 010 (Notiz, offen).
- `README.md:294–398` — Card-/Panel-/Admin-Dokumentation (Ist-Stand).
- Code: `www/health-o-mat-card.js`, `www/health-o-mat-panel.js`, `frontend.py`,
  `panel.py`, `ws_api.py`, `ui_store.py`, `entity.py`, `__init__.py`, `store.py`,
  `sensor.py`, `button.py`, `config_flow.py`, `const.py`.
- Vorbild: [`Popoboxxo/AbstrHActor`](https://github.com/Popoboxxo/AbstrHActor)
  (Management-Panel, Root+Subentries, ES-Module+esbuild, admin-gated WS).

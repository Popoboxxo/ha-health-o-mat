# Laborwerte — Entity-Oberfläche & Eingabe-Entities (Optionsraum)

> **STATUS: BRAINSTORM — NICHT BESCHLOSSEN.**
> Dieses Dokument sammelt und bewertet Optionen für zwei offene Schwachstellen der
> Laborwerte-Domäne (REQ-HOM-122 + Erweiterung REQ-HOM-123…129). Es enthält **keine
> REQ-IDs, keinen Plan, keine Implementierungsfreigabe**. Nichts hier ist entschieden;
> die Empfehlungen in §6 sind Vorschläge für die nächste Entscheidungsrunde.
>
> **Basis:** `main` = `b18e96e` · `docs/superpowers/specs/2026-10-30-lab-values-design.md`
> (REQ-HOM-122) · `docs/superpowers/specs/2026-11-01-lab-values-batch-and-visibility-design.md`
> (REQ-HOM-123…129, geplant) · Code-Stellen sind mit `datei:zeile` belegt.

---

## 1. Verifizierter Ist-Zustand

### 1.1 Entity-Zahl pro Person (ein Config-Entry)

| Bereich | Sensoren | Binary | Number | Select | Text | Button | Summe |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trinken | 7 | 1 | 2 | – | 1 | 6 | **17** |
| Blutdruck | 6 | 1 | 5 | – | – | 1 | **13** |
| Wohlbefinden | 2 | – | 1 | 1 | – | 10 | **14** |
| **Laborwerte** | **29** | **9** | – | – | – | – | **38** |
| **Summe (Defaults)** | 44 | 11 | 8 | 1 | 1 | 17 | **82** |

Belege: `sensor.py:31-59`, `binary_sensor.py:27-41`, `number.py:24-49`,
`button.py:20-38`, `select.py:16-17`, `text.py:19-20`. Die 29 Labor-Sensoren sind
`LAB_MARKERS` (`const.py:192-485`); die 9 Warn-Binaries entstehen aus den Kategorien
**ohne** `other` (`const.py:175-186`, `binary_sensor.py:32-39`). Jeder Custom-Marker
erhöht die Zahl um **1 Sensor**; ein Custom-Marker in einer bereits vorhandenen
Kategorie erzeugt **keine** zusätzliche Warn-Binary.

> Die 82 ist die Rechnung mit den Default-Quick-Drinks (4). `quick_drinks` ist
> options-getrieben — die Trinken-Summe wächst mit jedem konfigurierten Quick-Drink.

### 1.2 Was die 38 Labor-Entities tatsächlich kosten

- Jeder `LabValueSensor` ist `state_class = MEASUREMENT` **mit** Einheit
  (`sensor.py:507-513`) → HA erzeugt **Langzeitstatistik (LTS) je Marker**, also
  **29 LTS-Streams pro Person**. Dazu kommt State-History bei jeder Wertänderung.
- Die 9 `binary_sensor`-Warnungen erzeugen State-History, **keine** LTS.
- `number`/`text`/`select`/`button` erzeugen laut HA-Regel keine LTS
  (`statistics.py:17-19` bestätigt das für dieses Repo) — aber `number`/`text`/`select`
  schreiben State-History, jeder Zwischenwert ist ein Recorder-Eintrag.
- Es gibt **keinen Personen-Namespace** in HA: alles landet in der globalen
  Entitätsliste; die einzige personspezifische Gruppierung ist das Device
  (`entity.py:26-31`).

### 1.3 Die drei heutigen Hebel

| Hebel | Wirkung | Grenze |
|---|---|---|
| `areas.labs = false` | entfernt **alle 38** Labor-Entities beim Plattform-Setup **und** den Panel-Tab | Alles-oder-nichts; keine Teilmengen |
| `lab_hidden_categories` | **nur Anzeige** im Panel (`ws_api.py:628`, `644-671`); keine Entity-Wirkung, kein Reload (`__init__.py:392-397`) | löst Problem A nicht |
| Manuelles Deaktivieren in HA | wirkt echt (keine States, keine LTS) | Handarbeit, nicht im Integration-Backup, kein Bulk |

### 1.4 Der entscheidende Befund für Gruppe A

Panel und Labs-Card lesen **den Store** (`ws_api.py:616-671`), nicht die Entity-States.
Daraus folgt:

> **Wer eine Marker-Entity nicht erzeugt oder deaktiviert, verliert keine Daten** —
> Panel, Card, Export und Verlauf zeigen weiterhin alles. Verloren gehen nur
> Automations-/State-Konsumenten, die konkrete `sensor.*`-Entities abonnieren, und
> die LTS des jeweiligen Markers. Das ist der eigentliche Hebel für alle
> A-Optionen: Entity-Reduktion ist eine **Darstellungs-/Recorder-Entscheidung**,
> keine Datenentscheidung.

---

## 2. Bewertungsmaßstab

Jede Option wird an fünf Kriterien gemessen:

1. **Entity-Anzahl** — wie viele der 38 fallen weg (dauerhaft, nicht nur im UI)?
2. **Recorder/LTS** — weniger States/LTS oder nur „aus dem Blickfeld"?
3. **`unique_id`-Sicherheit** — bleibt `{entry_id}_lab_<marker>` unverändert?
4. **Persistenz** — überlebt die Entscheidung Backup/Restore? (Optionen ja, Registry nein)
5. **Aufwand** — S/M/L inkl. Migrations-/Doku-Anteil.

---

## 3. Gruppe A — Entity-Oberfläche reduzieren

Übersicht vorab:

| Option | Entities danach | Recorder/LTS | Bestand betroffen | Breaking | Aufwand |
|---|---|---|---|---|---|
| A1 `lab_enabled_markers` | 1 … 29 + gefilterte Warn-Binaries | sinkt (bewusst) | nein (Default = alle) | nein | M |
| A2 `enabled_default = False` | ca. 10–14 (nur Neuinstallationen) | sinkt (neu) | nein | nein | S |
| A3 `entity_category = diagnostic` | 38 | **unverändert** | nein | nein | S |
| A4 Kategorie-Aggregat | 9 statt 29 | LTS je Marker **weg** | ja | **MAJOR** | M |
| A5 `hidden_categories` erweitern | je Auswahl | sinkt | ja | **MAJOR** | M |
| A6 Device je Kategorie | 38 | unverändert | nein (Device-Umzug) | nein | M |
| A7 Bulk-Registry-Aktionen | 38 (User entscheidet) | sinkt nur bei Klick | nein | nein | M |
| A8 Lazy-Erzeugung bei 1. Wert | 0 … 29 | sinkt | nein (Bestand bleibt) | nein | M |
| A9 Outsider: Event-Entity | 1–2 | LTS je Marker weg | ja | MAJOR | M–L |

### A1 — Option `lab_enabled_markers` (Whitelist)

**Kurzbeschreibung.** Eine neue `entry.options["lab_enabled_markers"]`-Liste legt fest,
für welche Marker überhaupt Entities erzeugt werden. Fehlt der Schlüssel = **alle**
(bestehendes Verhalten). Zusätzlich werden Warn-Binaries nur für Kategorien erzeugt, in
denen mindestens ein aktivierter Marker liegt.

**HA-Pattern-Fit.** Passt: Options-Wert + Filter im Plattform-Setup, exakt das Muster von
`areas` (`areas.py:8-13`) und der Custom-Marker-Menge. Änderung braucht einen Reload —
der Pfad existiert bereits für die Marker-Menge (`__init__.py:407-427`), muss aber um
den neuen Schlüssel erweitert werden (der Snapshot enthält `hidden`, verglichen wird
heute nur `markers`, `__init__.py:414`). UI: `SelectSelector(multiple=True)` im
Options-Wizard (Basics oder eigener Schritt „Laborwerte").

**Aufwand / Dateien.** **M** — `const.py` (Options-Key + Default-Konstante), `logic.py`
(Normalizer, HA-frei), `sensor.py` + `binary_sensor.py` (Filter), `__init__.py`
(Snapshot/Reload-Vergleich), `config_flow.py` (Mehrfachauswahl), `ws_api.py`
(`panel_data`/Settings, falls Admin-UI), `backup.py`, `diagnostics.py`,
`strings.json`/`translations/{de,en}.json`, Tests.

**Bestehende Installationen.** Kein Effekt, solange der Schlüssel fehlt (Default = alle).
Nach expliziter Auswahl verschwinden die abgewählten Entities aus dem State; die
Registry-Einträge bleiben als unavailable/orphan liegen (genau wie `areas.labs=false`).
`unique_id`s bleiben unverändert; erneutes Aktivieren bringt dieselbe Entity zurück.
Backfill gibt es nicht: LTS/History starten erst ab Reaktivierung, der Store behält
aber die vollen Werte.

**Risiken/Nachteile.** Zwei Wahrheiten (Store zeigt alles, Entities zeigen eine Teilmenge)
können verwirren — muss dokumentiert werden. Custom-Marker brauchen eine eigene
Behandlung (mit in die Liste oder separater Schalter). Eine abgewählte Kategorie
verliert auch ihre Warn-Binary, obwohl Werte außerhalb des Referenzbereichs vorliegen
können — bewusste, aber erklärungsbedürftige Semantik. Options-/Reload-Test nötig.

**Nutzen.** Problem A: **hoch** (echte Reduktion, persistenzfest, kein Breaking).
Problem B: keiner.

### A2 — `entity_registry_enabled_default = False` für seltene Marker

**Kurzbeschreibung.** Ein „Kernset" häufiger Marker (`LAB_CORE_MARKERS` in `const.py`,
ca. 10–14) wird normal erzeugt; alle übrigen bekommen
`_attr_entity_registry_enabled_default = False`. Sie existieren in der Registry, sind
aber standardmäßig deaktiviert: kein State, keine History, keine LTS — bis der Nutzer
sie in der UI aktiviert.

**HA-Pattern-Fit.** Sehr gut: das ist das native HA-Muster für „vorhanden, aber nicht
standardaktiv" (`Entity.entity_registry_enabled_default`). Keine neue Option, keine
neue UI, kein Reload-Pfad.

**Aufwand / Dateien.** **S** — `const.py` (Kernset), `sensor.py` (eine Property im
`LabValueSensor`), ggf. `binary_sensor.py`, Tests.

**Bestehende Installationen.** **Kein Effekt**: das Flag wirkt nur bei der
**Erstregistrierung**. Bereits registrierte Entities bleiben aktiviert. Für den Bestand
hilft nur A7 (expliziter Bulk-Deaktivieren-Knopf) oder Handarbeit.

**Risiken/Nachteile.** Das Kernset ist eine Meinung des Integrationsautors — Marker, die
jemand braucht, „fehlen" scheinbar (die Entity ist da, aber deaktiviert; das ist in der
UI sichtbar). Kein Bestandsnutzen. Wer einen Marker später aktiviert, bekommt keine
rückwirkende LTS.

**Nutzen.** Problem A: **mittel** (nur Neuinstallationen, dort aber sofort spürbar).
Problem B: keiner.

### A3 — `entity_category = diagnostic` für Marker/Kategorien

**Kurzbeschreibung.** Die Labor-Entities werden als Diagnose-Entities einsortiert
(`EntityCategory.DIAGNOSTIC`). In der Geräteansicht landen sie im Bereich „Diagnose",
aus automatisch generierten Dashboards fallen sie heraus.

**HA-Pattern-Fit.** Sauberes HA-Muster — aber es ist eine **Kategorisierung**, kein
Filter. Diagnostic-Entities sind weiterhin aktiv, schreiben States und LTS.

**Aufwand / Dateien.** **S** — `sensor.py`/`binary_sensor.py` (je eine Klassen-Property),
Reload/Neustart für die Umgruppierung, Translation unverändert.

**Bestehende Installationen.** Additiv; Entities bleiben unter derselben `entity_id`
erreichbar, wandern nur in der UI in den Diagnose-Bereich.

**Risiken/Nachteile.** **Löst Problem A nicht** — die Recorder-/LTS-Kosten bleiben
identisch. Erzeugt ein falsches „erledigt"-Gefühl. Für Eingabe-Entities (Gruppe B) wäre
`EntityCategory.CONFIG` das Gegenstück, aber diese Entities sind Dateneingabe, keine
Konfiguration — dort nicht anwenden.

**Nutzen.** Problem A: **niedrig** (nur optisch). Problem B: keiner.

### A4 — Ein Aggregat-Sensor je Kategorie

**Kurzbeschreibung.** Statt 29 Einzel-Sensoren ein Sensor je Kategorie (9, mit `other`
10), dessen `native_value` z. B. die Anzahl außerhalb des Referenzbereichs ist und der
alle letzten Marker-Werte als JSON-Attribut trägt.

**HA-Pattern-Fit.** Als Muster im Repo vorhanden (`HistoryDrinksSensor`,
`HISTORY_ATTRIBUTE_LIMIT`, `sensor.py:145-175`) — aber Attribute sind **keine**
Historie: HA schreibt sie nur als Teil des States, sie sind nicht wie LTS abfragbar,
nicht grafisch als Einzelreihe nutzbar und werden im Recorder bei jeder Änderung
mitgeschrieben.

**Aufwand / Dateien.** **M** für den Code (`sensor.py`, ggf. `logic.py`), **L** für die
Migration, wenn die 29 Einzel-Sensoren ersetzt werden: 29 `unique_id`s werden verwaist,
Dashboards/Automationen brechen, LTS endet.

**Bestehende Installationen.** Als **Ersatz** breaking (MAJOR + Migrationshinweis); als
**Ergänzung** wächst die Entity-Zahl — das Gegenteil des Ziels.

**Risiken/Nachteile.** Laborwerte sind der klassische Langzeit-Trend-Fall; der Verlust
der Einzel-LTS ist der Killer. Ein Attribut-JSON wächst und ist im Recorder teurer als
ein schlanker Einzel-State. Keine Referenzbereichs-/`in_range`-Logik je Marker mehr in
Automationen.

**Nutzen.** Problem A: **niedrig** (nur wenn Breaking akzeptiert wird, dann hoch — aber
teuer). Problem B: keiner. **Empfehlung: nicht verfolgen.**

### A5 — `lab_hidden_categories` semantisch auf Entity-Erzeugung erweitern

**Kurzbeschreibung.** Die heute reine Anzeige-Option soll zusätzlich steuern, welche
Kategorie-Entities erzeugt werden.

**HA-Pattern-Fit.** Kein neues Muster — aber **semantische Überladung**: ein Schlüssel
mit zwei Bedeutungen („im Panel ausblenden" vs. „Entity nicht erzeugen"). Bestandsnutzer
haben die Option zum Ausblenden benutzt und würden ungefragt Entities verlieren.

**Aufwand / Dateien.** **M** — `sensor.py`, `binary_sensor.py`, `__init__.py`
(Reload bei Änderung), Admin-UI-Text, Tests. Kein neuer Options-Key.

**Bestehende Installationen.** **Breaking**: Wer Kategorien nur ausgeblendet hat, verliert
plötzlich Entities samt LTS-Fortschreibung. Das ist genau die Erwartung, die man nicht
brechen will.

**Risiken/Nachteile.** Zwei Bedeutungen in einem Feld; keine Möglichkeit, „nur ausblenden"
und „nicht erzeugen" getrennt zu wählen. Rückschritt gegenüber A1, das beides trennt.

**Nutzen.** Problem A: mittel, aber mit hohem Erklärungs- und Breaking-Risiko.
**Empfehlung: nicht verfolgen; A1 statt A5.**

### A6 — Ein Device je Kategorie

**Kurzbeschreibung.** Zusätzlich zum Personen-Device ein Device je Labor-Kategorie
(`via_device` auf das Personen-Device), an das die Marker-Sensoren gehängt werden.

**HA-Pattern-Fit.** Technisch sauber (`DeviceInfo(identifiers=…, via_device=…)`), aber
Device-Registry-Einträge sind **kein** Filter: Entities bleiben global sichtbar und
recorden unverändert.

**Aufwand / Dateien.** **M** — `entity.py`/`sensor.py`/`binary_sensor.py`
(`device_info`-Aufbau), Tests; Device-Registry wächst um bis zu 10 Einträge pro Person.

**Bestehende Installationen.** Additiv; Entities ziehen beim Reload um, `entity_id` bleibt.
Kein Datenverlust.

**Risiken/Nachteile.** Mehr Registry-Objekte, mehr UI-Klicks, keine Recorder-Entlastung.
Die Geräteansicht wird kleinteiliger statt übersichtlicher.

**Nutzen.** Problem A: **niedrig** (nur Gruppierung). Problem B: keiner.
**Empfehlung: höchstens später als UI-Politur.**

### A7 — Bulk-Aktionen in der Admin-UI (Entity-Registry)

**Kurzbeschreibung.** Ein Admin-Bereich „Laborwert-Entities" mit Knöpfen wie „Nur
Kernmarker aktiv", „Alle aktiv", „Alle deaktivieren". Die Aktion schreibt direkt in die
Entity-Registry (`registry.async_update_entity(entity_id, disabled_by=RegistryEntryDisabler.USER)`),
gefiltert auf die Labor-`unique_id`s des Entries.

**HA-Pattern-Fit.** Registry-Schreibzugriff ist HA-nativ, aber **nicht** backup-fest und
nicht in `entry.options` sichtbar. Der Nutzer kann jede Entscheidung in der UI wieder
rückgängig machen (disabled_by = USER, nicht INTEGRATION).

**Aufwand / Dateien.** **M** — neues WS-Kommando + Admin-UI (`ws_api.py`,
`www/health-o-mat-panel-admin.js`/`panel.js`), Tests; ggf. `statistics`-Hinweis.

**Bestehende Installationen.** Kein Automatismus — nur auf Klick. Damit ist es der
einzige gefahrlose Weg, **Bestandsinstallationen** zu entlasten, ohne eine neue Option
einzuführen. Nach einem Reset/Neuaufbau der Registry sind die Entscheidungen weg
(Registry ist nicht im Integration-Backup).

**Risiken/Nachteile.** Zwei Quellen der Wahrheit (Optionen vs. Registry) können
auseinanderlaufen; Support-Fall „warum ist die Entity weg?". Kein Effekt für Nutzer, die
die Admin-UI nicht öffnen.

**Nutzen.** Problem A: **mittel** (Bestand, manuell). Problem B: keiner.
**Empfehlung: als Begleiter zu A2, nicht als alleinige Lösung.**

### A8 — Lazy-Erzeugung: Entity erst beim ersten Wert (zusätzliche Idee)

**Kurzbeschreibung.** Beim Setup werden **keine** Marker-Sensoren erzeugt. Sobald für
einen Marker der erste aktive Wert geschrieben wird, wird seine Entity dynamisch
(`async_add_entities` nach dem Setup) nachgezogen; ab dann bleibt sie. Ergebnis: die
Entity-Zahl entspricht den tatsächlich getrackten Markern, nicht dem Katalog.

**HA-Pattern-Fit.** Erlaubt, aber weniger deklarativ als ein statischer Entity-Satz:
Plattform hält den `async_add_entities`-Callback, der Coordinator-Listener reagiert auf
Store-Änderungen. `unique_id` bleibt `{entry_id}_lab_<marker>` — stabil und
wiederverwendbar. Kein Reload nötig.

**Aufwand / Dateien.** **M** — `sensor.py` (Callback + Listener), `binary_sensor.py`
(Warn-Binary erst bei erster Kategorie mit Daten), `logic.py` („welche Marker haben
aktive Werte"), Tests; `__init__.py` unverändert.

**Bestehende Installationen.** Unverändert — bestehende Entities bleiben registriert.
Optionaler Cleanup („Entities ohne je einen Wert entfernen") wäre ein separater,
bewusster Schritt.

**Risiken/Nachteile.** Entity erscheint erst später: Dashboards/Automationen, die vor dem
ersten Wert gebaut werden, finden sie nicht (UI-Automation kann keine Referenz auf eine
noch nicht existierende Entity anlegen). „Warum ist der Sensor plötzlich da?".
Dynamische Entities sind in HA erlaubt, aber ungewohnter als ein fester Satz.

**Nutzen.** Problem A: **hoch** (proportional zum echten Gebrauch). Problem B: niedrig.

### A9 — Outsider: eine `event`-Entity je Person (verworfen)

**Kurzbeschreibung.** Eine einzige `event`-Entity feuert bei jedem neuen Laborwert
(`event_type = "lab_value"`, Marker/Wert/Einheit als Attribute); optional ein Sensor
„letzter Marker". Entity-Zahl: 1–2.

**HA-Pattern-Fit.** `EventEntity` ist ein legitimes HA-Muster für Ereignisse — aber
Events haben **keinen Zustand** und **keine LTS**; Dashboards können keinen Verlauf
binden. Es bricht den REQ-HOM-122-Vertrag „ein Sensor je Marker".

**Aufwand / Dateien.** **M–L** (neue Plattform `event.py`, `PLATFORMS`, Tests,
Dokumentation), Breaking für alle, die heute Marker-Sensoren abonnieren.

**Bestehende Installationen.** Breaking; 29 Sensoren würden zu Orphans.

**Risiken/Nachteile.** Kein Verlauf, keine Automation auf „Wert > X" ohne Event-Trigger;
der Nutzen (1 Entity) wird mit dem Verlust der Kernfunktion erkauft.

**Nutzen.** Problem A: hoch auf dem Papier, real zu teuer. **Empfehlung: nicht verfolgen.**

---

## 4. Gruppe B — Eingabe-Entities

Heute schreiben ausschließlich: Services (`add_lab_value`, geplant `add_lab_report`),
Panel-Formular, Labs-Card, CSV/Backup-Import. Blutdruck hat `number`-Eingaben +
Speichern-Button (`number.py:164-199`, `button.py:124-151`), Wohlbefinden `select` +
Buttons (`select.py:20-70`, `button.py:154-174`) — die Asymmetrie ist real.

### B1 — `select` (Marker) + `number` (Wert) + `text` (Einheit) + `button` (Speichern)

**Kurzbeschreibung.** Vier Entities bilden den Eingabeweg nach dem BP-Muster:

| Entity | `unique_id` | Inhalt |
|---|---|---|
| `select` | `{entry_id}_select_lab_marker` | Marker-Key (Katalog + Custom) |
| `number` | `{entry_id}_number_lab_value` | Wert (Rohwert, `step: any`) |
| `text` | `{entry_id}_text_lab_unit` | Einheit (leer = kanonisch) |
| `button` | `{entry_id}_button_lab_save` | „Laborwert speichern" |

Der Entwurf liegt im bestehenden `inputs`-Dict (`store.py:799-811`) unter eigenen Keys
(`lab_marker`/`lab_value`/`lab_unit`) — **kein Schema-Bump**, weil `inputs` seit v2 ein
generisches Dict ist.

**HA-Pattern-Fit.** Exakt das Haus-Muster für Eingaben (BP). `select`-Optionen sind rohe
Marker-Keys; für lokalisierte Anzeigen bräuchte es
`entity.select.<key>.state.<marker>`-Übersetzungen (29 Keys × 3 Dateien) — oder man
akzeptiert englische Keys. Wertvalidierung/Umrechnung passiert im Button über die
vorhandene HA-freie Logik (`resolve_lab_marker`, `coerce_lab_number`,
`convert_lab_value`, `logic.py:1076-1108`).

**Aufwand / Dateien.** **M** — `select.py` (neue Klasse), `number.py` (neue Klasse),
`text.py` (neue Klasse), `button.py` (Speichern + Validierung), `store.py` (Typ-Hinweis
`set_inputs` von `int | None` auf `str | None` erweitern; **kein** Schema-Bump),
`const.py` (Options-Keys), `strings.json`/`translations`, Tests.

**Bestehende Installationen.** Rein additiv; keine bestehende `unique_id` berührt.
Vier neue Entities pro Person.

**Risiken/Nachteile.**
- **Zustands-Leichen:** `text`/`number`/`select` halten den Entwurf als State — jede
  Änderung ist ein Recorder-Eintrag (keine LTS). Nach dem Speichern muss der Entwurf
  gezielt geleert werden.
- **`clear_inputs()` löscht heute ALLE Inputs** (`store.py:808-811`) — ein BP-Speichern
  würde einen offenen Labor-Entwurf mitlöschen. Braucht getrennte Clear-Pfade oder
  eigene Keys mit gezieltem Löschen.
- Einheiten: `require_explicit_unit` (nur `urine_protein_creatinine_ratio`) muss auch im
  Entity-Pfad greifen; sonst stillschweigend falsche Werte.
- Der Button-Fehler ist Prosa (`HomeAssistantError`), nicht der strukturierte
  `{code, params}`-Vertrag — das ist REQ-HOM-127, nicht diese Runde.

**Nutzen.** Problem B: **hoch** (symmetrisch zu BP, ohne neue UI). Problem A: negativ
(+4 Entities).

### B2 — Ein `text`-Feld mit Parser + `button`

**Kurzbeschreibung.** Ein `text`-Entity nimmt eine Zeile wie `alt 32 U/L` oder
`Kreatinin 1.1 mg/dL`; ein Parser (HA-frei) löst Marker-Alias/Katalog/Custom, Wert und
Einheit auf; ein `button` speichert. Zwei Entities.

**HA-Pattern-Fit.** Das Muster existiert im Repo für Getränke (`text.py:23-63`,
`parser.py`). **Wichtige Grenze:** ein HA-`text`-Entity ist **einzeilig** (max. 255
Zeichen, `mode: text`), kein Mehrzeilenfeld. Ein echtes Paste-Feld für ganze Befunde
gehört in Panel/Card — dort entsteht es mit REQ-HOM-123 ohnehin.

**Aufwand / Dateien.** **M** — `text.py` (neue Klasse), neuer HA-freier Parser in
`logic.py`/eigenem Modul, `button.py`, `const.py`, Tests. Keine 29 Select-Übersetzungen.

**Bestehende Installationen.** Additiv (2 neue Entities, neue `unique_id`s).

**Risiken/Nachteile.** Tippfehler und unbekannte Marker sind teurer als ein Dropdown;
lange Marker-Keys (`urine_protein_creatinine_ratio`) sind mobil kaum tippbar;
Einheiten-Raten ist bei Laborwerten gefährlich (g/g vs. mg/g); Discoverability schwach
(„was muss ich hier eingeben?"). Keine strukturierte Fehlermeldung.

**Nutzen.** Problem B: **mittel**; Problem A: neutral (+2).

### B3 — `number` je Marker (29 Stück)

**Kurzbeschreibung.** Je Marker eine `number`-Entity; das Setzen der Zahl bucht sofort
einen Wert (Muster `WellbeingInputNumber`, `number.py:201-235`). Kein Speichern-Button.

**HA-Pattern-Fit.** Für kleine, feste Mengen HA-idiomatisch; bei 29 Markern kippt es.
`number` erzeugt keine LTS, aber State-History.

**Aufwand / Dateien.** **M** — `number.py` (Klasse je Marker oder Factory), `logic.py`
(Zeitstempel/Validierung), Tests. `unique_id`-Muster `{entry_id}_number_lab_<marker>`.

**Bestehende Installationen.** Additiv, aber **+29 Entities** — verschärft Problem A.

**Risiken/Nachteile.**
- **Akzidentelle Buchungen:** jede Automation/Dashboard-Interaktion schreibt eine echte
  Messung mit `ts = now`; kein `report_ref`, kein Berichts-`ts`.
- **Semantik-Konflikt:** `native_value` müsste „letzter Wert" *oder* „Eingabe" sein;
  HA ruft `async_set_native_value` bei gleichem Wert nicht erneut auf — eine
  Korrektur/Bestätigung desselben Werts ist nicht möglich.
- Keine Einheitenwahl (nur kanonisch), keine Alt-Einheiten.

**Nutzen.** Problem B: **mittel**, Problem A: **stark negativ**.
**Empfehlung: nur in Kombination mit A1 und nur für eine Handvoll Marker denkbar.**

### B4 — Keine Eingabe-Entities; Pfade dokumentieren (Status quo)

**Kurzbeschreibung.** Es bleibt bei Services, Panel-Formular, Labs-Card und CSV-Import;
README/CONCEPT-UI dokumentieren diese Wege explizit als „Eingabe".

**HA-Pattern-Fit.** Kein neues Muster; die UI-Pfade existieren bereits
(`health-o-mat-labs-card.js`, Panel-Formular) und werden mit REQ-HOM-123 um den
Mehrzeilen-Dialog erweitert.

**Aufwand / Dateien.** **S** — nur Doku (`README.md`, ggf. `docs/CONCEPT-UI.md`).

**Bestehende Installationen.** Unverändert.

**Risiken/Nachteile.** Die Asymmetrie bleibt; Automations-Nutzer müssen Services
aufrufen; kein „schneller Wert" aus der Entity-Liste.

**Nutzen.** Problem B: **niedrig–mittel** (anerkannt, aber nicht gelöst); Problem A:
neutral. **Valide, wenn A Priorität hat.**

### B5 — HA-Helper (`input_text`) + Automation (nicht Integrationssache)

**Kurzbeschreibung.** Nutzer legt HA-Helper an und eine Automation, die den Helper-Inhalt
per Service in die Integration schreibt.

**HA-Pattern-Fit.** Kein Integrations-Code, aber auch kein Produkt-Feature: Boilerplate
pro Nutzer, keine Validierung/Einheitenlogik, keine Übersetzungen, keine
Fehlerbehandlung.

**Aufwand / Dateien.** **S** — nur Doku/FAQ („Escape Hatch").

**Bestehende Installationen.** Keine.

**Risiken/Nachteile.** Fehlerhafte Werte landen ungeprüft im Store; Verantwortung
wandert zum Nutzer; nicht supportbar.

**Nutzen.** Problem B: **niedrig**. **Nur als dokumentierter Ausweg erwähnen.**

---

## 5. Gruppe C — Kombinationen & Presets

### C1 — A2 + B1 (+ A7 für den Bestand)

Kernmarker standardmäßig aktiv, Rest `enabled_default = False`; dazu der
4-Entity-Eingabeweg aus B1; für Bestandsinstallationen ein Bulk-Knopf aus A7.
Neue Installationen starten mit ca. 10–14 aktiven Marker-Sensoren statt 29 und haben
trotzdem einen sauberen Eingabeweg. Kein Breaking, keine neue Option, kein
Migrationspfad.

### C2 — A4 + B4

Kategorie-Aggregate statt Einzel-Sensoren, Schreiben bleibt Service/Panel/Card.
Auf dem Papier die radikalste Reduktion (9 statt 29), praktisch der teuerste Weg:
Breaking, LTS-Verlust, Attribut-JSON statt Einzel-Historie. **Nur als bewusste
„Compact-Mode"-Entscheidung mit MAJOR-Release denkbar.**

### C3 — A1 + Presets + B1

Explizite Marker-Whitelist in `entry.options`, Presets als Startpunkt, B1 als Eingabe.
Persistenzfest (Optionen überleben Backup/Restore), kein Registry-Drift, volle Kontrolle.
Aufwand höher (Options-UI, `panel_data`, Backup, Diagnostics), dafür die „saubere"
Variante.

### C4 — Marker-Presets (Baustein, keine eigene Option)

Benannte Marker-Mengen als Konstante, z. B.:

| Preset | Inhalt (Vorschlag) |
|---|---|
| `core` | alt, ast, ggt, creatinine, egfr, crp, tsh, hemoglobin, leukocytes, platelets, cholesterol_total, ldl, hdl, triglycerides |
| `kidney_liver` | liver + kidney (9 Marker) |
| `all` | alle 29 (Default/Status quo) |

Presets sind nur Daten (`const.py`) und ein UI-Shortcut — kein Framework. Sie können
entweder A1 (Options-Whitelist) oder A2 (Kernset) oder A7 (Registry-Bulk) befüllen.
**Wichtig:** Das Preset ist ein Startpunkt, keine Sperre; der Nutzer muss danach
einzeln nachjustieren können.

---

## 6. Empfohlene Kombinationen

### R1 — „Eine Runde Zeit": A2 (Kernset) + A7 (Bulk-Knopf) + B1

**Was gebaut wird.** `LAB_CORE_MARKERS` in `const.py`; `enabled_default = False` für alle
übrigen Marker-Sensoren; ein Admin-Knopf „Nur Kernmarker aktiv" (A7) für den Bestand;
der 4-Entity-Eingabeweg aus B1 (select/number/text/button) mit Entwurf im
`inputs`-Dict.

**Warum.** Kleinster Eingriff mit echtem Effekt auf **beide** Probleme: neue
Installationen starten bei ~10–14 statt 38 Labor-Entities; der Bestand kann per Klick
nachziehen; die Eingabe-Asymmetrie verschwindet ohne neues UI-Konzept. Keine
`unique_id`-Änderung, kein Schema-Bump, kein Breaking. Aufwand **M** (S für A2, M für
B1, M für A7 — A7 kann in eine Folgerunde).

**Grenze.** A2 wirkt nicht rückwirkend; ohne A7 bleibt der Bestand bei 38 Entities.
Das Kernset ist eine Design-Entscheidung, die begründet werden muss.

### R2 — „Sauber und persistenzfest": C3 (A1 + Presets + B1)

**Was gebaut wird.** `lab_enabled_markers` (Default = alle) + Preset-Auswahl im
Options-Wizard + B1. Warn-Binaries nur für Kategorien mit mindestens einem aktiven
Marker.

**Warum.** Die einzige Variante, bei der die Entscheidung in `entry.options` lebt und
damit Backup/Restore überlebt; kein Registry-Drift; der Reload-Pfad für geänderte
Marker-Mengen existiert bereits (`__init__.py:407-427`) und muss nur erweitert werden.
Default = alle heißt: **kein Bestandsnutzer verliert ungefragt eine Entity.**
Aufwand **L** (Options-UI, `panel_data`/Admin, Backup, Diagnostics, Übersetzungen,
Tests).

### R3 — „Radikal, wenn A dominiert": A8 (Lazy) + B4 (Doku)

**Was gebaut wird.** Marker-Sensoren entstehen erst mit dem ersten aktiven Wert;
Eingabe bleibt bei Panel/Card/Service (B4, ggf. plus REQ-HOM-123-Dialog).

**Warum.** Die Entity-Zahl ist exakt so groß wie der tatsächliche Gebrauch — ohne
Options-UI, ohne Kernset-Meinung. Aufwand **M–L**. Preis: Entities erscheinen zeitlich
versetzt; Dashboards/Automationen vor dem ersten Wert finden sie nicht. Nur sinnvoll,
wenn „Entity-Flut" das dominante Problem ist und die Eingabe über UI akzeptiert wird.

> **Wenn wirklich nur eine Runde Zeit ist: R1.** A2 ist eine Property, B1 ist ein
> bekanntes Haus-Muster, A7 ist nachrüstbar. R2 ist die Zielarchitektur, R3 die
> Option für später.

---

## 7. Was NICHT (Anti-Pattern / Over-Engineering)

- **A4 als Ersatz der Einzel-Sensoren.** 29 `unique_id`s verwaist, LTS je Marker weg,
  Attribute sind keine Historie. Laborwerte sind der klassische Langzeit-Trend —
  genau dafür braucht man die Einzel-Sensoren.
- **A3 als alleinige Maßnahme.** `entity_category` ist Kosmetik: kein Recorder-Effekt,
  aber der Eindruck, das Problem sei gelöst.
- **A5 (hidden → Entity-Erzeugung).** Semantische Überladung eines bestehenden
  Anzeige-Feldes; bricht die Erwartung von Bestandsnutzern. Wenn Auswahl, dann A1.
- **A6 (Device je Kategorie) als Lösung für A.** Mehr Registry-Objekte, null
  Recorder-Entlastung.
- **A9 (Event-Entity) als Ersatz.** Bricht den REQ-HOM-122-Vertrag, kein Verlauf, keine
  LTS, keine Automation auf Zustände.
- **B3 (29 `number`-Entities).** Verschärft A, erzeugt akzidentelle Buchungen, kein
  `ts`/`report_ref`, Einheiten-/Alt-Einheiten-Logik fehlt, `native_value`-Konflikt.
- **B2 als Mehrzeilen-Parser-Entity.** HA-`text` ist einzeilig; ein Paste-Feld gehört in
  Panel/Card (REQ-HOM-123), nicht in eine Entity.
- **B5 als Produktantwort.** Helper + Automation ist Nutzer-Boilerplate ohne Validierung.
- **Ein neues „Lab-Entity-Framework"** (eigene Registry, Label-System, generische
  Visibility-Engine). Zwei Optionen + ein Attribut reichen.
- **`unique_id`s „aufräumen" oder umbenennen.** Verboten; Entitäten verschwinden nur
  durch Nicht-Erzeugen/Deaktivieren, nie durch ID-Änderung.

---

## 8. Offene Fragen an den Nutzer (entscheidungsrelevant, max. 5)

1. **Was ist das Hauptziel?** Weniger Entities in der Liste, weniger Recorder-/LTS-Last
   oder weniger UI-Rauschen? (A2/A8 vs. A1 vs. A3.)
2. **Welche Marker sind „Kern"?** Ist ein festes Kernset (A2/R1) akzeptabel, oder soll
   der Nutzer die Auswahl explizit treffen (A1/R2)? Presets als Startpunkt ok?
3. **Wo soll die Auswahl leben?** In `entry.options` (backup-/restore-fest, A1) oder in
   der Entity-Registry (HA-nativ, aber nicht im Backup, A2/A7)?
4. **Eingabe:** Reicht der bestehende UI-/Service-Weg (B4), soll es der 4-Entity-Weg
   (B1) sein, oder ein Freitext-Parser (B2)? Darf B1 vier zusätzliche Entities
   erzeugen?
5. **Ist Breaking erlaubt?** Dürfen Entities verschwinden (A4/A5, MAJOR mit
   Migrationshinweis), oder gilt „nichts verschwindet ungefragt" als harte Grenze?

---

## 9. Threat-Model-Kurzcheck (Datenschutz / Recorder)

**1. Was wird gebaut?** Keine neuen Datenquellen, keine neuen Abhängigkeiten. Neue
Steuerflächen: Options-Whitelist (A1), Registry-Schreibzugriffe (A7), ggf. Eingabe-
Entities (B1). Gesundheitsdaten bleiben im Store; Panel/Card lesen sie wie heute.

**2. Was könnte schiefgehen?**
- **Marker-Identitäten leaken:** `lab_enabled_markers` verrät, welche Marker eine Person
  trackt (z. B. Tacrolimus → Transplantationskontext). Das ist dieselbe Klasse wie
  `lab_custom_markers`, das bereits redigiert wird (`diagnostics.py:53-63`).
- **Backup-Divergenz:** A7-Entscheidungen (Registry) sind **nicht** im Backup; nach
  Restore sind Entities wieder aktiv → unerwartete Recorder-Last. A1/A2 sind
  reproduzierbar (Option bzw. Default greift bei Neu-Registrierung).
- **Akzidentelle Buchungen:** B3/B1-Entwürfe können über Automationen/Dashboards
  ungewollt Werte schreiben (B1 mindert das durch expliziten Speichern-Button).
- **LTS-Lücken:** Deaktivierte Marker erzeugen keine Statistik; beim Aktivieren wird
  **nicht** rückwirkend backgefüllt. Das ist kein Datenverlust (Store vollständig),
  aber ein Erwartungsbruch bei Statistik-Nutzern.
- **Diagnostics:** Aggregate (A4) würden mehrere Messwerte in einem State-Attribut
  bündeln — der Recorder speichert sie mit; Diagnostics bleibt redigiert.

**3. Was wird dagegen getan?**
- Neue Optionsschlüssel in die Redaktionsliste von `diagnostics.py` (wie
  `lab_hidden_categories`, `lab_ref_overrides`).
- Neue Optionsschlüssel additiv in `backup.lab_options` (kein Format-Bump, Muster
  `backup.py:167-179`).
- Keine automatischen Registry-Änderungen ohne Nutzeraktion (A2 nur Default bei
  Erstregistrierung; A7 nur auf Klick); `disabled_by = USER`, nicht INTEGRATION.
- B1 speichert nur auf expliziten Button-Druck; keine „Zahl = Buchung"-Automatik.
- Doku: „Entities sind eine Sicht auf den Store, keine Datenquelle" + LTS-Hinweis.

**4. Konsequenzen.** Weniger States/LTS = kleinere Recorder-DB und weniger
Langzeit-Abfragen — positiv. Risiko bleibt die Erwartungs- und Support-Last
(„warum fehlt mein Marker?"), nicht der Datenschutz. Kein Export nach `/config/www`,
keine neuen Tokens, keine Cloud-Calls.

**Recorder-Matrix (Kurzform):**

| Option | States/History | LTS |
|---|---|---|
| A1 | nur aktive Marker | nur aktive Marker (ab Aktivierung) |
| A2 | nur aktivierte Marker | nur aktivierte Marker (ab Aktivierung) |
| A3 | unverändert | unverändert |
| A4 | 9 Aggregate (Attribute größer) | **keine** Einzel-LTS mehr |
| A5 | nur nicht ausgeblendete Kategorien | dito |
| A6 | unverändert | unverändert |
| A7 | nur aktivierte Entities | nur aktivierte Entities |
| A8 | nur Marker mit Daten | dito |
| B1 | 4 zusätzliche State-Quellen (Entwurf) | keine |
| B3 | 29 zusätzliche State-Quellen | keine |

---

## 10. Belege (verifiziert am Code, `main` = `b18e96e`)

- Entity-Aufbau: `custom_components/health_o_mat/sensor.py:25-60`, `:495-549`;
  `binary_sensor.py:21-42`, `:92-123`; `number.py:18-49`; `button.py:14-38`;
  `select.py:13-17`; `text.py:16-20`.
- Katalog: `const.py:175-186` (10 Kategorien inkl. `other`), `:192-485` (29 Marker).
- `unique_id`/Device: `entity.py:22-32`.
- Bereiche/Areas: `areas.py:1-14`.
- Hidden nur Anzeige: `ws_api.py:616-671`; Reload-Semantik `__init__.py:381-432`.
- Lab-Options-Snapshot: `__init__.py:102-122`.
- `inputs`-Dict: `store.py:799-811`.
- BP-Eingabemuster: `number.py:164-199`, `button.py:124-151`.
- Recorder-Regel (number/text ohne LTS): `statistics.py:1-19`.
- Diagnostics-Redaktion: `diagnostics.py:53-63`.
- Backup-Lab-Options: `backup.py:160-179`.
- Batch-/Panel-Erweiterung (Eingabe-UI): `docs/superpowers/specs/2026-11-01-lab-values-batch-and-visibility-design.md` §6.

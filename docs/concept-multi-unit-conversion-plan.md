# Konzept: Multi-Unit-Speicherung/-Konvertierung — Analyse + Optionen + Umsetzungsplan

**Status:** ENTWURF (Analyse-Auftrag, keine Implementierung) · **Datum:** 2026-11-20
**Auftrag:** Senior-Developer-Analyse auf Zuruf des Orchestrators (Second-Hand-Audit-Referenzen
B-1/C-1, C-2, B-2, B-3 grounden + 3 neue Dauer-Anforderungen des Nutzers einordnen + offene
Architekturfrage als Entscheidungsvorlage, nicht als Antwort).

> **Hinweis zur Vertrauenswürdigkeit der Eingabe:** Der Auftrag kam mit Second-Hand-Audit-IDs
> (B-1/C-1, C-2, B-2, B-3), deren Originalbericht nicht vorliegt. Diese Analyse hat jede ID
> gegen den echten Code geprüft, statt sie zu übernehmen (Abschnitt 0). Zwei der vier IDs
> (B-2, B-3) beschreiben echte, aber **anders benannte** Lücken, eine (B-1/C-1) ist eine
> **echte Inkonsistenz mit falscher Begründung**, eine (C-2) ist **nur zur Hälfte zutreffend**.
> Keine der vier IDs deckt sich mit den B-1…B-4-Kürzeln aus `docs/PLAN-AUDIT-2026-11-03.md`
> (das sind E2E-Lücken, bereits erledigt) — unterschiedliche Nummerierung, nicht derselbe Fund.

---

## 0. Grounding der vier Second-Hand-Audit-Befunde

| ID (second-hand) | Behauptung | Status | Befund |
|---|---|---|---|
| **B-1/C-1** | „`daily_goal_ml` Bounds/Validierungs-Problem" | **BESTÄTIGT** (Inkonsistenz, nicht Abwesenheit) | Drei Validierungsorte für `daily_goal_ml`, drei verschiedene Grenzen: `config_flow.py:417-419` (`vol.Range(min=500, max=10000)`), `number.py:81-82` (`_attr_native_min_value = 500`, `_attr_native_max_value = MAX_AMOUNT_ML` = 10000), **aber** `ws_api.py:268` (`SETTINGS_SCHEMA`, der vom Admin-Panel genutzte WS-Pfad `set_settings`) erlaubt nur `vol.Range(min=1)` — **keine Obergrenze, keine 500-Untergrenze**. Ein Admin kann über das Panel `daily_goal_ml` auf z. B. `1` oder `50_000_000` setzen, was Options-Flow und Number-Entity explizit verhindern. Das ist der reale Bug: **keine fehlende Validierung, sondern drei divergierende Validierungen für dasselbe Feld.** |
| **C-2** | „fehlende Längenlimits / Admin-Gating-Problem" | **TEILWEISE BESTÄTIGT** | **Längenlimits:** bestätigt fehlend — `ws_api.py:270` (`person_display: str`, kein `vol.Length`), `ws_api.py:277-278` (`quick_drinks[].key`/`label`: `str`, kein `vol.Length`). Einzige vorhandene Längengrenze im ganzen Modul ist `LAB_REPORT_REF_MAX_LEN = 500` (`const.py:700`) für `report_ref`. Unbegrenzte Strings landen in `entry.options` (Persistenz) und im Frontend (Rendering) — kein akuter Crash, aber ein unbegründetes Fehlen einer sonst überall vorhandenen Disziplin. **Admin-Gating:** NICHT bestätigt als Problem — `ws_api.py:1988-2016` implementiert ein fail-closed Muster (`is_admin_connection()` + `require_admin()`-Wrapper, greift auch ohne `require_admin` in Fake-Umgebungen) und wird an mind. 7 Stellen (`:2280,2298,2333,2383,2410,2431,2452` u.a.) konsequent angewendet. Die Admin-Gating-Hälfte der Behauptung scheint eine Verwechslung oder ein veralteter Stand zu sein. |
| **B-2** | „nur 8 von 41 LAB_MARKERS durch Oracle-Test gedeckt" | **BESTÄTIGT** (präzise) | `LAB_MARKERS` hat exakt 41 Einträge (`const.py:196`, geprüft per `len()`). Der **JS↔Python-Paritätstest** `test_req_hom_134_panel_and_card_display_oracle_matches_python` (`tests/test_card_js.py:3406`) nutzt genau **8 verschiedene Marker-Keys** in seinen `specs` (`creatinine`, `bilirubin_total`, `hemoglobin`, `cholesterol_total`, `triglycerides`, `ft4`, `ft3`, `hematocrit` — die 8 Grenzfall-Paare wiederholen 4 davon). Der **reine Python-Oracle-Test** `test_req_hom_134_convert_lab_display_value_all_factory_defaults` (`tests/test_logic.py:2446`) deckt zwar alle `LAB_DEFAULT_UNITS`-Einträge ab, das sind aber nur **12 von 41** Markern (`const.py` `LAB_DEFAULT_UNITS`, geprüft per `len()`); die übrigen 29 Marker (darunter 10 der 22 Marker, die überhaupt `alt_units` besitzen) werden von keinem Oracle-Test berührt. Die Zahl „8" aus dem Second-Hand-Bericht trifft exakt den JS-Paritätstest — die eigentliche Lücke ist größer (bis zu 41, praktisch relevant: die 22 Marker mit nicht-leeren `alt_units`). |
| **B-3** | „Wellbeing-Mirror ohne Paritätstest" | **TEILWEISE BESTÄTIGT** (präziser: kein *Oracle*-Paritätstest, aber ein Cross-Check existiert) | `wellbeingScore()` ist in **zwei** JS-Dateien unabhängig implementiert (`www/health-o-mat-card.js:813`, `www/health-o-mat-panel-base.js:1147`), beide Kommentare nennen sich ausdrücklich „spiegelt `logic.wellbeing_score`". Es GIBT einen Cross-Check-Test `test_req_hom_112_card_and_panel_resolve_the_same_wellbeing_score` (`tests/test_panel_js.py:775`), der Karte und Panel gegeneinander UND gegen eine **hart codierte** Erwartungstabelle (`_SCORE_RULE_CASES`, `tests/test_panel_js.py:641-654`) prüft. Der entscheidende Unterschied zum Lab-Oracle-Muster (§0 B-2): Der Lab-Test ruft `py_logic.convert_lab_display_value(...)` zur Laufzeit auf und vergleicht JS-Output dagegen (echter Oracle, kann nicht driften). Der Wellbeing-Test vergleicht JS nur gegen **von Hand eingetippte** Literale, die angeblich `logic.wellbeing_score` entsprechen — es gibt eine SEPARATE Python-Testgruppe (`tests/test_logic.py:1084-1173`), die `logic.wellbeing_score` pinnt, aber **keine einzige Testfunktion ruft beide (Python-Funktion + JS-Literal-Tabelle) im selben Lauf gegeneinander auf**. Ändert sich `WELLBEING_STATES` (neue Stufe, Reihenfolge), kann `logic.wellbeing_score` sich ändern, ohne dass `_SCORE_RULE_CASES` automatisch mitzieht — ein manuelles Nachziehen ist nötig und wird von keinem Test erzwungen. Das ist die präzise Lücke: **kein Oracle-Test, nur ein Literal-Paritätstest.** |

**Einordnung für den Rest des Dokuments:** B-2 und B-3 sind Testabdeckungslücken derselben
Klasse (JS↔Python-Spiegel ohne/mit unzureichendem Oracle) und gehören in denselben
Umsetzungsschritt (§3, Schritt 5). B-1/C-1 und der Längenlimit-Teil von C-2 sind
Validierungs-Inkonsistenzen derselben Klasse (ein Feld, mehrere Validierungsorte, keine
gemeinsame Quelle) und gehören in denselben Schritt (§3, Schritt 1).

---

## 1. Entity-Inventar: Mengen/Einheiten-relevante Entities

Gelesen: `entity.py`, `sensor.py`, `number.py`, `select.py`, `text.py`, `binary_sensor.py`,
`button.py`, `logic.py`, `parser.py`, `const.py`, `config_flow.py`, `store.py`, `ws_api.py`.

### 1.1 Gemeinsames Fundament

- `unique_id` = `f"{entry.entry_id}_{key}"` (`entity.py:25`), **ausnahmslos** ab Entity #1,
  über eine gemeinsame Basisklasse `HealthOMatEntity(CoordinatorEntity)`.
- `device_info` ab Entity #1, ein Device pro Person (`entity.py:26-31`).
- `suggested_object_id` fest auf Englisch gepinnt (`entity.py:35-54`) — unabhängig von
  `has_entity_name`/`translation_key`, die den Anzeigenamen lokalisieren.
- **Kein zentrales Einheiten-Register**: jede Plattformdatei trägt ihre Einheiten als
  String-Literal (`"mL"`, `"mmHg"`, `"%"`, `"BPM"`) oder liest sie aus `LAB_MARKERS`
  (`marker_def["canonical_unit"]`). Es gibt kein `UNIT_OF.<domain>`-Konzept, das Drinks, BP
  und Labor gemeinsam bedienen würde.

### 1.2 Trinken (Area `drink`)

| Entity | Plattform | `unique_id`-Suffix | Einheit | Speicherort des Werts | Speicherort der Einheit |
|---|---|---|---|---|---|
| `TodaySensor` | sensor | `sensor_drinks_today` | `mL` (fix, `SensorDeviceClass.VOLUME`) | abgeleitet (on-read, `logic.today_sums`) aus `store` → `drinks[].ml` | **nicht gespeichert** — Einheit ist Code-Konstante (`sensor.py:87`) |
| `PercentSensor`, `LifetimeSensor`, `DrinksTrendSensor`, `GoalStreakSensor`, `CaffeineTodaySensor`, `HistoryDrinksSensor` | sensor | je eigener Key | `%`, `mL`, dimensionslos | abgeleitet aus `drinks[]` | wie oben, Code-Konstante |
| `DailyGoalNumber` | number | `number_daily_goal` | `mL` | **`entry.options["daily_goal_ml"]`** (seit Audit C-2/REQ: einzige Quelle der Wahrheit) | Code-Konstante (`_attr_native_unit_of_measurement = "mL"`, `number.py:91`) |
| `CustomAmountNumber` | number | `number_custom_amount` | `mL` | `entry.runtime_data.custom_amount_ml` (Laufzeit-Spiegel, nicht in `entry.options`!) | Code-Konstante |
| `FreeTextDrinkEntity` | text | `text_freetext` | — (Eingabe, kein Output-Zustand mit Einheit) | schreibt via `parser.parse()` **sofort kanonisch in ml** nach `store.add_drink()` | Freitext kann `l`/`L` enthalten (`parser.py:100-106`), wird aber **beim Parsen verworfen** — die Original-Einheit des Nutzers ("ich habe 0,5l eingegeben") wird **nicht persistiert**, nur `ml` |
| Store-Schema `drinks[]` | — | — | — | `{"ml": int, "type": str, ...}` (`store.py:431-461`) | **kein `unit`-Feld, kein `reported_*`-Feld** — strikt kanonisch, kein Multi-Unit-Vorbild |

**Befund Trinken:** Volle Kanonisierung am Eingabepunkt, kein Rückweg. Wer in Liter eingegeben
hat, kann diese Tatsache nirgends mehr auslesen.

### 1.3 Blutdruck (Area `bp`)

| Entity | Plattform | `unique_id`-Suffix | Einheit | Speicherort |
|---|---|---|---|---|
| `LastReadingSensor` (×3: sys/dia/pulse) | sensor | `sensor_last_{sys,dia,pulse}` | `mmHg`/`BPM` (Parameter beim Setup, `sensor.py:51-52`) | abgeleitet aus `store` → `readings[]` |
| `BloodPressureHistorySensor`, `BloodPressureCategorySensor`, `BpTrendSensor` | sensor | je eigener Key | `mmHg` bzw. kategorial | abgeleitet |
| `ThresholdNumber` (×2: sys/dia) | number | `number_threshold_{sys,dia}` | `mmHg` | `entry.runtime_data.{sys,dia}_threshold` (**Laufzeit-Spiegel, NICHT `entry.options`** — anders als `daily_goal_ml`, siehe §0 B-1/C-1: diese Inkonsistenz ist der Nachbar-Fall, keine Persistenz-Garantie über Neustart hinaus außer über `_options_updated`-Sync) |
| `InputNumber` (×3: sys/dia/pulse) | number | `number_input_{sys,dia,pulse}` | `mmHg`/`BPM` | `store.inputs()` (persistiert, überlebt Neustart, REQ-HOM-104) |
| Store-Schema `readings[]` | — | — | — | `{"sys": int, "dia": int, "pulse": int|None, ...}` (`store.py:575-612`) — **keine Einheit gespeichert, implizit immer mmHg/BPM, kein `unit`-Feld** |

**Befund Blutdruck:** Wie Trinken — keine Einheit im Store, keine Alt-Einheit, keine
Umrechnung überhaupt (mmHg ist die einzige im klinischen Alltag genutzte Einheit, daher
bisher kein Problem — aber auch kein Vorbild für Multi-Unit).

### 1.4 Wohlbefinden (Area `wellbeing`)

| Entity | Plattform | Einheit | Speicherort |
|---|---|---|---|
| `WellbeingSelect` | select | dimensionslos (Status-Key) | `store.set_wellbeing()` → `wellbeing.status` |
| `WellbeingInputNumber` | number | dimensionslos (1..N) | wie oben, über `logic.wellbeing_key_for_score`/`wellbeing_score` Hin- und Rückabbildung |
| `WellbeingScoreSensor`, `WellbeingSinceSensor` | sensor | dimensionslos bzw. Timestamp | abgeleitet, **keine eigene Persistenz** (`sensor.py:471-481`: „Der Score ist rein abgeleitet (on-read, keine eigene Persistenz)") |

**Befund Wohlbefinden:** Kein Einheiten-Thema im engeren Sinn (dimensionslose Skala), aber
der **Score-Berechnungscode ist dupliziert** (Python + 2× JS, siehe §0 B-3) — strukturell
dieselbe Fehlerklasse wie eine Einheiten-Umrechnung, die an mehreren Stellen dupliziert
divergieren kann.

### 1.5 Labor (Area `labs`) — das einzige Multi-Unit-Vorbild im Code

| Komponente | Datei | Verhalten |
|---|---|---|
| `LAB_MARKERS[*]` | `const.py:196-621` | 41 Marker, je `canonical_unit` + `alt_units: {unit: factor}` (gemeldet → kanonisch) |
| `LabValueSensor` | `sensor.py:495-513` | `native_unit_of_measurement = marker_def["canonical_unit"]` — **State ist immer kanonisch**, keine Alt-Einheit als State sichtbar |
| `store.add_lab_reading()` | `store.py:692-741` | Persistiert **beide** Repräsentationen pro Messung: `value`/`unit` (kanonisch) **und** `reported_value`/`reported_unit` (Originaleingabe) — **das einzige Store-Schema im Projekt, das eine Messung in zwei Einheiten persistiert** |
| `logic.convert_lab_display_value()` + `lab_display_decimals()` | `logic.py:1317+`, `1361+` | **Nur Anzeige** (D1 aus REQ-HOM-134, explizit als Nicht-Ziel dokumentiert: „Keine Änderung an `native_unit_of_measurement`… Store bleibt kanonisch") — kein Produktionsaufrufer, nur Oracle für Tests und für die zwei JS-Spiegel |
| `entry.options["lab_default_units"]` | `const.py` `OPTION_LAB_DEFAULT_UNITS` | Pro-Person-Override der **Anzeige**-Einheit (0.22.0, REQ-HOM-134) — **ändert nichts an der Persistenz**, nur daran, in welcher Einheit die Admin-Maske/Karte den kanonischen Wert zeigt |

**Zentraler Befund für die gesamte Analyse:** Das Projekt hat bereits **zwei verschiedene,
unvereinheitlichte Muster** für „mehr als eine Einheit":

1. **Lab-Readings (Store-Ebene):** persistiert kanonisch **und** reported — aber nur als
   Nebenprodukt der Eingabe-Historie, nicht als generisches Feature; kein Lese-Pfad, der
   gezielt „gib mir Marker X in Einheit Y" beantwortet, außer dem reinen Anzeige-Converter.
2. **Lab-Display (REQ-HOM-134, UI-Ebene):** konvertiert nur beim Rendern, ändert nie den
   Store, ist explizit als Nicht-Speicherung dokumentiert (Design-Spec §4 „Nicht-Ziele").

Die neue Anforderung 1 des Nutzers („tatsächlich in verschiedenen Einheiten persistieren UND
zurücklesen können") liegt **zwischen** diesen beiden bestehenden Mustern und wird von
keinem vollständig erfüllt.

---

## 2. Architektur-Optionen für Multi-Unit-Speicherung/-Konvertierung

Alle drei Optionen respektieren die eisernen Regeln: `unique_id` ändert sich nie,
`on-read`-Fenster statt Reset-Job (nicht direkt betroffen, aber als Präzedenzmuster
relevant), Options für nachträglich Korrigierbares vs. `entry.data` für Strukturelles,
ein Coordinator pro Entry mit `update_interval=None`.

### Option A — Kanonische Speicherung + On-Read-Konvertierung (Status quo erweitern)

**Idee:** Jede Messung bleibt in genau einer kanonischen Einheit gespeichert (wie heute bei
Labor: `value`/`unit`). Jede gewünschte Alt-Einheit wird **bei jedem Lesezugriff** über
einen Faktor umgerechnet — nicht nur für die Anzeige (wie heute, REQ-HOM-134), sondern auch
für einen neuen Lese-Pfad (Service/WS-Kommando `get_value(marker, unit)`), der den Faktor
zur Abfragezeit anwendet.

| Kriterium | Bewertung |
|---|---|
| `unique_id`-Stabilität | Unproblematisch — keine neuen Entities pro Einheit nötig |
| On-read vs. Reset-Job | Passt zum bestehenden Projekt-Idiom (vgl. Tagesfenster-Berechnung) |
| Options vs. `entry.data` | Faktoren/Marker-Katalog bleiben Code (`const.py`), keine Options-Änderung nötig; nur die Anzeige-Präferenz ist Options (bereits so, REQ-HOM-134) |
| Persistenz-Garantie für Anforderung 1 | **Schwach:** „lesen in Einheit Y" wird erfüllt, aber die Rückgabe ist **immer** aus der kanonischen Zahl neu berechnet — es gibt keinen persistierten Beleg, in welcher Einheit der Nutzer *ursprünglich gemeldet* hat (außer bei Labor, wo `reported_unit` schon mitläuft) |
| Migrationsrisiko | **Minimal** — keine Schema-Änderung, kein `STORE_SCHEMA_VERSION`-Bump nötig, falls nur ein Lese-Pfad ergänzt wird |
| Aufwand | Niedrig — Lab-Konverter existiert bereits (`convert_lab_display_value`), muss nur von „nur Anzeige" auf „produktiv aufrufbar" erweitert werden; für Drinks/BP wäre ein neues Einheiten-Vokabular nötig (heute keins) |
| Erfüllt Anforderung 2 (manuell erweiterbar)? | **Gut** — neue Einheit = neuer Eintrag in `alt_units`-Dict, kein Code-Deploy für reine Faktor-Ergänzung (sofern das Dict aus einer Konfigurationsdatei statt `const.py` käme — siehe §4 Q3) |
| Nachteil | Kein echter Audit-Trail „was hat der Nutzer in Einheit X gemeldet" für Drinks/BP, weil dort (anders als Labor) nie eine `reported_*`-Spur eingeführt wird, es sei denn man übernimmt das Lab-Muster (→ das ist dann Option B) |

### Option B — Mehrere persistierte Repräsentationen je Messung (Lab-Muster verallgemeinern)

**Idee:** Jede Messung (Labor **und** künftig ggf. Drinks/BP) speichert **beide** Werte:
kanonisch (`value`/`unit`) + original (`reported_value`/`reported_unit`) — exakt das
bestehende `add_lab_reading()`-Schema, verallgemeinert auf alle Domänen, die Multi-Unit
brauchen.

| Kriterium | Bewertung |
|---|---|
| `unique_id`-Stabilität | Unproblematisch — betrifft nur den Store-Eintrag, keine Entity-Struktur |
| On-read vs. Reset-Job | Neutral — betrifft Persistenz, nicht Fenster-Berechnung |
| Options vs. `entry.data` | Unverändert — reine Store-Schema-Erweiterung |
| Persistenz-Garantie für Anforderung 1 | **Stark** — die Originaleinheit ist dauerhaft belegt, kein Rückrechnungsfehler über Faktor-Drift möglich (wird 1x beim Schreiben festgehalten) |
| Migrationsrisiko | **Mittel** — `STORE_SCHEMA_VERSION`-Bump nötig (aktuell 5 → 6), wenn Drinks/BP ein neues Feld bekommen (`unit`, `reported_unit`); bestehende Migration-Kette in `store.py` (`migrate_store_data`) kennt das Muster bereits aus v5 (Labor-Readings hinzufügen) — **kein** `async_migrate_entry`/Entity-Versions-Bump nötig, das ist reine Store-Interna, keine Config-Entry-Version |
| Aufwand | Mittel — Store-Schema + Migration + CSV-Export/-Import (`exporter.py`/`importer.py`) müssen die neuen Felder kennen, sonst Datenverlust beim Export |
| Erfüllt Anforderung 2 (manuell erweiterbar)? | **Gut**, identisch zu Option A (Faktor-Katalog unabhängig von der Speicherstrategie) |
| Nachteil | Speicherwachstum (zwei Zahlen statt einer pro Messung) — bei Drinks (hochfrequent, täglich mehrere Einträge) spürbarer als bei Labor (selten); zwei Repräsentationen können bei einem Faktor-Fix nachträglich **inkonsistent** werden (die bereits gespeicherte `reported_value` bleibt bei einer späteren Korrektur des `alt_units`-Faktors stehen, die `value` wird dann nicht automatisch nachgezogen — braucht eine explizite Korrekturregel, falls Faktoren je geändert werden, vgl. §5.1 der Lab-Default-Units-Spec zum `urea`-Faktor-Fehler) |

### Option C — Haupt-Entity + abgeleitete Read-Only-View-Entities (Nutzerfrage, siehe §4 Q1)

**Idee:** Für jede Messgröße gibt es eine „Haupt-Entity" (kanonischer Wert, wie heute) plus
zusätzliche, read-only „Ableitungs-Entities" je Alt-Einheit (z. B. `sensor.creatinine_mg_dl`
neben `sensor.creatinine` mit kanonisch µmol/L).

| Kriterium | Bewertung |
|---|---|
| `unique_id`-Stabilität | **Risikoreich bei Einführung, stabil danach** — jede neue Ableitungs-Entity bekommt einmalig eine neue `unique_id` (`{entry_id}_{key}_{unit}` o. ä.); solange das Schema beim ersten Rollout fix steht, keine spätere Änderung nötig. Das größte Risiko ist der **Entity-Zuwachs**: bei 22 Markern mit `alt_units` × ggf. mehreren Alt-Einheiten je Marker entstehen potenziell 20–40 neue Entities pro Person — WP-D (`docs/PLAN-AUDIT-2026-11-03.md` T-2/T-3) hat genau diesen Druck bereits als Trigger definiert (fünfte Datendomäne / `const.py` ≥ 1200 Zeilen) |
| On-read vs. Reset-Job | Passt — Ableitungs-Entity berechnet bei jedem Read aus der Haupt-Entity, kein Cache/Reset-Job nötig (wie `convert_lab_display_value` heute) |
| Options vs. `entry.data` | Welche Ableitungs-Entities aktiv sind, wäre ein Options-Feld (nachträglich korrigierbar — Nutzer schaltet eine Alt-Einheits-Ansicht ein/aus) |
| Persistenz-Garantie für Anforderung 1 | **Mittel** — „Lesen in Einheit Y" ist pro Entity direkt abfragbar (gut für Automationen/Dashboards, die eine feste Entity mit fester Einheit erwarten), aber die Ableitungs-Entity speichert selbst nichts Neues — sie ist nur eine zweite Sicht auf denselben kanonischen Wert, also inhaltlich näher an Option A als an Option B |
| Migrationsrisiko | **Hoch**, wenn das Schema der Ableitungs-Entities (welche Einheiten, welche Marker) sich später ändert — jede Änderung an „welche Ableitungs-Entities existieren" ist nach der eisernen Regel ein Breaking Change (`unique_id`/Entity-Menge ändert sich), siehe Nicht-Ziele der REQ-HOM-134-Spec, die genau das für die aktuelle Lösung ausgeschlossen hat |
| Aufwand | Hoch — neue Plattform-Logik (welche Marker × welche Einheiten × welche Sprache), HA-Entity-Explosion, Übersetzungsaufwand (`strings.json`/`translations/*.json` pro Ableitungs-Entity) |
| Erfüllt Anforderung 2 (manuell erweiterbar)? | **Schlecht** — eine neue Alt-Einheit heißt eine neue Entity heißt Code-Deploy + Versions-Bump + ggf. Migration; widerspricht der Nutzeranforderung „ohne starres, nur code-seitig erweiterbares System" am direktesten von allen drei Optionen |
| Vorteil | Für HA-native Konsumenten (Automationen, Lovelace, Statistik-Dashboards), die eine feste `entity_id` mit fester `native_unit_of_measurement` erwarten, ist eine echte Entity oft komfortabler als ein WS-Kommando mit Parameter — **das ist der Kern-Trade-off, den der Nutzer selbst entscheiden muss** (siehe §4 Q1) |

### Querschnitts-Einschätzung (keine Vorwegnahme der Nutzerentscheidung)

- Option A und B sind **nicht exklusiv** — B ist eine Verstärkung von A (B speichert
  zusätzlich das, was A nur bei jedem Read neu berechnet). Eine naheliegende Kombination:
  **A als Basismechanik (Konverter, Einheiten-Katalog) + B selektiv dort, wo ein Audit-Trail
  der Original-Einheit sinnvoll ist** (Labor hat das schon; Drinks/BP könnten es optional
  bekommen, falls Anforderung 1 das verlangt).
- Option C ist orthogonal — sie betrifft die **Darstellung** (wie viele und welche
  Entities), nicht die **Speicherung**. Sie kann auf A oder B aufsetzen: Ableitungs-Entities
  könnten entweder live konvertieren (auf A aufsetzend) oder eine persistierte
  Alt-Repräsentation lesen (auf B aufsetzend).
- Die bestehende REQ-HOM-134-Lösung (Anzeige-Einheiten, 0.22.0) ist **genau Option A, aber
  nur für den UI-Rendering-Pfad**, nicht für einen produktiven Lese-Service/WS-Endpunkt. Der
  nächste Schritt für Anforderung 1 ist strukturell klein, wenn A gewählt wird (Konverter
  existiert, muss nur einen echten Aufrufer bekommen) und strukturell groß, wenn C gewählt
  wird (neue Entity-Fläche).

---

## 3. Stufenplan: 4 Audit-Befunde + 3 neue Anforderungen gebündelt

Reihenfolge ist **Abhängigkeits-, nicht Prioritäts**-gesteuert. Schritte, die auf die offene
Nutzerentscheidung (§4 Q1) warten, sind explizit markiert.

```
Schritt 1 (unabhängig) ──► Schritt 2 (unabhängig) ──► Schritt 5 (unabhängig)
Schritt 3 ──► WARTET AUF Q1 (Architekturentscheidung) ──► Schritt 4 ──► Schritt 6
Schritt 7 (Doku) nach jedem Schritt fortlaufend
```

### Schritt 1 — Validierungs-Inkonsistenz beheben (grounded B-1/C-1 + Längenlimit-Teil von C-2)

**Ziel:** Eine Quelle der Wahrheit für `daily_goal_ml`-Grenzen; Längenlimits für
`person_display`, `quick_drinks[].key/label` (und ggf. weitere ungeprüfte Textfelder).

- `daily_goal_ml`: `ws_api.SETTINGS_SCHEMA` auf `vol.Range(min=500, max=MAX_AMOUNT_ML)`
  angleichen (identisch zu `config_flow.py`/`number.py`) — oder besser: die Grenze als
  gemeinsame Konstante in `const.py` definieren (`MIN_DAILY_GOAL_ML`, `MAX_DAILY_GOAL_ML`)
  und von allen drei Stellen referenzieren lassen, damit eine zukünftige Änderung nicht
  wieder divergiert.
- Neue Konstanten `MAX_PERSON_DISPLAY_LEN`, `MAX_QUICK_DRINK_LABEL_LEN`,
  `MAX_QUICK_DRINK_KEY_LEN` in `const.py` (Vorbild: `LAB_REPORT_REF_MAX_LEN`); Anwendung in
  `ws_api.SETTINGS_SCHEMA` **und** `config_flow.py` (beide Schreibpfade).
- **Kein Zusammenhang mit Multi-Unit** — eigenständig, kann sofort und unabhängig von §4
  umgesetzt werden.
- **Admin-Gating-Teil von C-2:** kein Handlungsbedarf — bereits korrekt (§0).

**Agenten:** `developer` (klein, lokal begrenzt, kein Architektur-Impact) reicht hier aus;
nur als Teil dieses Bündels hier mitgeführt, weil es second-hand mitgemeldet wurde.

### Schritt 2 — Test-Coverage-Lücke Labor-Oracle schließen (grounded B-2)

**Ziel:** Der JS↔Python-Paritätstest deckt **alle** Marker mit nicht-leeren `alt_units`
(22 von 41), nicht nur 8.

- `test_req_hom_134_panel_and_card_display_oracle_matches_python` (`tests/test_card_js.py`):
  `specs`-Liste auf alle 22 Marker mit `alt_units` erweitern (automatisiert generieren statt
  Literal-Liste, z. B. `[(key, 100.0, unit) for key, m in LAB_MARKERS.items() if m["alt_units"] for unit in m["alt_units"]]`), damit neue Marker mit `alt_units` die Liste automatisch mitwachsen lassen statt erneut vergessen zu werden.
- `test_req_hom_134_convert_lab_display_value_all_factory_defaults` (`tests/test_logic.py`)
  bleibt auf `LAB_DEFAULT_UNITS` beschränkt (das ist korrekt — Werksdefaults sind per
  Definition 12), aber eine **zusätzliche** Testfunktion sollte **alle** 41 Marker mit
  `canonical_unit` als Self-Factor-1-Fall plus alle `alt_units`-Paare gegen
  `convert_lab_display_value` prüfen (Rundtrip-Eigenschaft, wie bereits bei
  `test_req_hom_134_convert_lab_display_value_roundtrip_reported_value`, aber über alle
  Marker statt nur `LAB_DEFAULT_UNITS`).

**Verbindung zu Anforderung 3** (Test-Coverage für Konvertierungslogik erhöhen): Dieser
Schritt ist die direkte Umsetzung von Anforderung 3 für den **bestehenden** Lab-Converter.
Jede neue Logik aus Schritt 4 (Multi-Unit für ggf. weitere Domänen) braucht einen äquivalenten
Oracle-Test nach demselben Muster — Schritt 2 liefert die Vorlage.

**Agenten:** `tester` (reine Testerweiterung, kein Produktionscode-Risiko) — ggf.
`developer`, falls die Marker-Iteration in `test_card_js.py` einen kleinen Hilfs-Export aus
`const.py` braucht.

### Schritt 3 — Nutzerentscheidung Q1 einholen (blockiert Schritt 4)

**Ziel:** Architekturfrage aus §4 Q1 beantworten lassen, bevor Multi-Unit-Speicherung für
neue Domänen umgesetzt wird. **Keine Implementierung in diesem Schritt.**

**Agenten:** `main_chat` (Entscheidung), ggf. `documenter` als Entscheidungsprotokoll
(Vorbild: `docs/PLAN-AUDIT-2026-11-03.md` §5 „Offene Entscheidungen").

### Schritt 4 — Multi-Unit-Speicherung/-Konvertierung umsetzen (Anforderung 1 + 2)

**Blockiert durch Schritt 3.** Konkrete Schritte hängen von der Entscheidung ab:

- **Bei Wahl A (On-Read-Konvertierung generalisieren):**
  1. Einheiten-Katalog aus `const.py` in eine **manuell erweiterbare** Struktur überführen
     (Anforderung 2) — z. B. ein eigenes, dokumentiertes Dict/YAML statt eines in `const.py`
     vergrabenen Literals, damit ein Hand-Edit ohne Code-Review-Hürde eine neue Einheit/einen
     neuen Faktor ergänzen kann (siehe §4 Q3 für die konkrete Formatentscheidung).
  2. Für Drinks/BP: ein neues `alt_units`-ähnliches Vokabular definieren (heute existiert
     keins außerhalb von Labor) — z. B. Volumeneinheiten (`mL`, `L`, `fl oz`) für Drinks,
     Druckeinheiten (`mmHg`, `kPa`) für BP, falls das die Produktanforderung ist.
  3. Neuen produktiven Lese-Pfad ergänzen (Service oder WS-Kommando), der
     `convert_lab_display_value`-artige Funktionen **nicht nur für die Anzeige**, sondern als
     öffentlichen Rückgabewert nutzt (heute explizit „kein Produktionsaufrufer" — das ändert
     sich mit dieser Anforderung, Nicht-Ziel-Liste der REQ-HOM-134-Spec muss für den neuen
     Scope widerrufen werden).
- **Bei Wahl B (zusätzliche Persistenz):**
  1. `STORE_SCHEMA_VERSION`-Bump + Migration in `store.py` (Vorbild v4→v5, Labor-Readings).
  2. `add_drink()`/`add_reading()` um `unit`/`reported_unit` erweitern (additiv, Rückwärtskompatibilität: altbestehende Einträge ohne dieses Feld bleiben lesbar, Default = aktuelle kanonische Einheit).
  3. `exporter.py`/`importer.py`/`backup.py`/`restore.py` um die neuen Felder erweitern (sonst
     Datenverlust bei Export/Backup — Vorbild-Fehler: REQ-HOM-134 hat `lab_default_units`
     bewusst NICHT in den Restore-Pfad aufgenommen, F14 — hier müsste bewusst entschieden
     werden, ob dasselbe YAGNI-Muster gilt oder nicht).
- **Bei Wahl C (Ableitungs-Entities):**
  1. Entity-Schema fixieren (`unique_id`-Suffix-Konvention für Ableitungs-Entities,
     z. B. `{entry_id}_lab_{marker_key}_{unit_slug}`) — **vor** dem ersten Rollout, weil
     danach nicht mehr änderbar.
  2. Options-Feld „welche Ableitungs-Entities aktiv" (nachträglich korrigierbar).
  3. Übersetzungen (`strings.json` + `translations/{de,en}.json`) pro Ableitungs-Entity.
  4. WP-D-Trigger (`docs/PLAN-AUDIT-2026-11-03.md` T-2/T-3) explizit gegen den neuen
     Entity-Zuwachs prüfen — ggf. selbst ein Trigger-Auslöser.

**Agenten:** `senior-developer` (Architektur-Impact, neue Datenmodelle, cross-cutting über
Store/Sensor/Options) — ggf. `principal-developer`, falls Wahl C mit hohem Entity-Zuwachs
kombiniert mit Schritt 1 (WP-D-Trigger) eskaliert.

### Schritt 5 — Wellbeing-Mirror-Oracle nachrüsten (grounded B-3)

**Ziel:** `logic.wellbeing_score` wird zur Laufzeit als echter Oracle in den JS-Paritätstest
eingebunden statt als von Hand gepflegte Literal-Tabelle.

- Neuer Testaufbau nach dem Lab-Oracle-Muster (§0 B-2-Vorbild, `test_card_js.py:3406`): Statt
  `_SCORE_RULE_CASES` hart zu codieren, soll der Test `logic.wellbeing_score(key)` **zur
  Testlaufzeit** aufrufen und das Ergebnis als Erwartungswert in den Node-Runner geben — die
  bestehenden Edge Cases (`None`, leerer String, Nicht-String, Case-Sensitivität) bleiben als
  Eingaben erhalten, nur die Erwartung kommt jetzt aus Python statt aus der Literal-Tabelle.
- Das deckt automatisch jede künftige Änderung an `WELLBEING_STATES` ab, ohne dass
  `test_panel_js.py` händisch nachgezogen werden muss.
- **Kein Zusammenhang mit Multi-Unit** — eigenständig, kann sofort umgesetzt werden
  (unabhängig von Schritt 3/4), aber derselbe Fehlerklasse wie Schritt 2 (JS-Spiegel-Drift)
  und damit Teil der „Test-Coverage für Konvertierungs-/Spiegel-Logik" aus Anforderung 3.

**Agenten:** `tester` (reine Testumstrukturierung) — ggf. `developer`, falls der Node-Runner
einen neuen Übergabemechanismus (Python-Werte → Node-Prozess-Argument) braucht.

### Schritt 6 — Dokumentation nachziehen

Nach Schritt 4 (abhängig von der Q1-Entscheidung): `docs/REQUIREMENTS.md` (neue REQ-ID über
`requirements`, falls die Anforderung über REQ-HOM-134 hinausgeht), Release-Notes-Eintrag
(💥 falls Wahl C mit Entity-Mengenänderung — MAJOR; additiv bei Wahl A/B — MINOR).

### Schritt 7 — Fortlaufende Dokumentation

Jeder Schritt oben bekommt sein eigenes `DECISION`-Protokoll (Architekturentscheidungen aus
Schritt 4) über `documenter`, analog zum bestehenden Muster in
`docs/PLAN-AUDIT-2026-11-03.md` §5.

---

## 4. Offene Fragen — der Nutzer entscheidet, nicht dieses Dokument

### Q1 — Haupt-Entity + abgeleitete Read-Only-View-Entities? (Nutzerfrage, verbatim)

> „Es ist aktuell unklar, welche Entities das System für einen gegebenen Messwert überhaupt
> anbietet (die Roh-Werte-Entity, Einheiten-Konvertierungs-Anzeige-Entities usw.). Möglicher
> Ansatz: ‚Haupt-Entities' für den eigentlichen Wert plus ‚abgeleitete Entities', die
> Read-Only-Views sind und denselben Wert in einer anderen Einheit repräsentieren. Macht das
> Sinn, und wie passt das zu den bestehenden `unique_id`/`device_info`/HACS-Konventionen des
> Projekts?"

**Trade-offs aus §2, zusammengefasst für die Entscheidung:**

- **Für Option C (Haupt + Ableitung):** HA-native Konsumenten (Automationen, Lovelace-Karten,
  Langzeitstatistik-Dashboards) können eine Alt-Einheit direkt als `entity_id` mit korrekter
  `native_unit_of_measurement` ansprechen, ohne eine Service-Antwort zu parsen. Das ist der
  „HA-idiomatische" Weg.
- **Gegen Option C:** Entity-Zuwachs (22 Marker mit `alt_units` × N Alt-Einheiten = potenziell
  20–40+ neue Entities/Person), was den bereits in `docs/PLAN-AUDIT-2026-11-03.md` WP-D
  dokumentierten Datei-/Entity-Wachstumsdruck (T-2/T-3) verstärkt. Zusätzlich: Jede Änderung
  an „welche Ableitungs-Entities existieren" ist nach der `unique_id`-Regel ein Breaking
  Change — die Entity-Menge muss beim ersten Rollout bereits endgültig sein, was Anforderung 2
  (manuelle Erweiterbarkeit ohne starres System) direkt widerspricht: eine neue Alt-Einheit
  für einen Marker würde eine neue Entity, also einen Versions-Bump + Migration erfordern.
- **Für Option A/B (kein neuer Entity-Typ):** Ein Lese-Service/WS-Kommando mit
  Einheiten-Parameter ist flexibler (neue Einheit = Daten-/Config-Änderung, kein
  Code-Deploy), passt besser zu Anforderung 2, aber verlangt von Automationen einen
  Service-Call statt eines einfachen Entity-State-Reads.
- **Kombination denkbar:** Haupt-Entity bleibt kanonisch (status quo), **eine begrenzte,
  bewusst kuratierte** Menge an Ableitungs-Entities für die praktisch relevantesten Fälle
  (z. B. nur die 12 `LAB_DEFAULT_UNITS`-Marker, nicht alle 41), kombiniert mit einem
  generischen Lese-Service für den Rest. Das ist aber selbst eine dritte Variante, die der
  Nutzer explizit mit entscheiden müsste — hier nicht vorweggenommen.

**Diese Frage wird hier bewusst NICHT beantwortet.**

### Q2 — Gilt Anforderung 1 (Multi-Unit-Persistenz) für alle Domänen oder nur für Labor?

Labor hat bereits eine `reported_*`-Spur (Option B de facto, aber nur als Nebenprodukt).
Drinks und BP haben **gar keine** Alt-Einheiten-Infrastruktur. Soll die neue Anforderung
Drinks/BP einschließen (z. B. „Trinkmenge in Liter oder Unzen zurücklesen"), oder ist der
Fokus ausschließlich Labor? Das bestimmt den Umfang von Schritt 4 erheblich.

### Q3 — Wie soll der „manuell erweiterbare" Einheiten-/Faktor-Katalog konkret aussehen?

Heute liegt `LAB_MARKERS`/`LAB_DEFAULT_UNITS`/`LAB_UNITS` fest in `const.py` (Python-Code,
Teil des versionierten Pakets — jede Änderung braucht einen Release). Anforderung 2 verlangt
„Hand-Ergänzung ohne starres, nur code-seitig erweiterbares System". Optionen, die der Nutzer
entscheiden müsste:

- **(a) Weiterhin `const.py`, aber dokumentiert als „hier manuell ergänzen"** — kein
  struktureller Umbau, aber jede Ergänzung bleibt ein Code-Release.
  (Das deckt sich nicht wirklich mit „ohne starres System".)
- **(b) Verlagerung in `entry.options` (pro Person ergänzbar, kein Release nötig)** — passt
  zur Options-Flow-Konvention des Projekts, aber globale/Werks-Defaults (für alle Personen)
  bräuchten dann einen separaten globalen Speicherort (Store? eigene Config-Datei?).
- **(c) Eigene JSON/YAML-Konfigurationsdatei im Integrationsverzeichnis**, die beim Start
  gelesen wird (kein `entry.options`, kein `const.py`-Release-Zwang) — näher an „Hand-Edit",
  aber neu für dieses Projekt (bisher gibt es kein Beispiel für eine solche externe
  Konfigurationsdatei außerhalb von `const.py`/`entry.options`).

Jede der drei Varianten hat unterschiedliche Auswirkungen auf Backup/Restore, Diagnostics und
Multi-Personen-Konsistenz (ist der Katalog pro Person oder global?) — diese Frage sollte vor
Schritt 4 zusammen mit Q1 entschieden werden, weil die Antwort auf Q3 auch die
Migrationsstrategie für Q1/Option B beeinflusst (ein Faktor-Fix in einer externen Datei
braucht keine Store-Migration, einer in `const.py` schon eher, da er mit einem Release kommt).

### Q4 — Soll Anforderung 3 (Test-Coverage) rückwirkend auch bestehende, bereits
veröffentlichte Marker ohne `alt_units` einschließen?

29 der 41 Marker haben `alt_units: {}` (keine Alt-Einheit definiert). Für diese ist ein
Oracle-Test über Konvertierung trivial (Faktor 1, keine Umrechnung) — lohnt sich ein
expliziter Test dafür, oder reicht die Beschränkung auf die 22 Marker mit echten
`alt_units`-Einträgen (praktisch relevanter Fall)? Beeinflusst den Umfang von Schritt 2.

---

## 5. Zusammenfassung für den Orchestrator

- **Vier Second-Hand-Befunde geerdet:** B-1/C-1 bestätigt (Validierungs-Inkonsistenz, nicht
  Fehlen), C-2 halb bestätigt (Längenlimits ja, Admin-Gating nein — das war schon korrekt),
  B-2 bestätigt und präzisiert (8/41 trifft den JS-Paritätstest exakt, die Python-Oracle-Lücke
  ist 12/41, die praktisch relevante Lücke bis zu 22/41), B-3 präzisiert (es gibt einen
  Cross-Check-Test, aber keinen echten Python-Oracle-Test — die Lücke ist subtiler als „gar
  kein Test").
- **Drei Architektur-Optionen** (A: On-Read-Konvertierung generalisieren, B: Mehrfach-
  Persistenz nach Lab-Vorbild, C: Haupt+Ableitungs-Entities) mit Trade-offs, keine Empfehlung
  vorweggenommen.
- **Sieben Umsetzungsschritte**, davon zwei sofort und unabhängig startbar (Schritt 1, 2, 5),
  einer explizit blockiert durch eine Nutzerentscheidung (Schritt 4 nach Schritt 3).
  Schritt 3 ist kein Implementierungsschritt, sondern die Weiterleitung von Q1 (und
  empfohlen: Q2/Q3/Q4) an `main_chat`.
- **Vier offene Fragen** für den Nutzer, inklusive der verbatim gestellten Haupt-/
  Ableitungs-Entity-Frage — absichtlich unbeantwortet gelassen.

**Nicht Teil dieser Analyse:** keine Code-Änderung, kein Commit, keine Entscheidung für den
Nutzer getroffen.

---

## 6. Nutzerentscheidungen (final, 2026-11-20)

| Frage | Entscheidung |
|---|---|
| Q1 — Architektur | **Kombination A+B**: On-Read-Konvertierung als Basismechanik überall, zusätzlich Mehrfach-Persistenz (kanonisch + `reported_*`) selektiv dort, wo ein Audit-Trail sinnvoll ist. Keine neuen Ableitungs-Entities (Option C verworfen — Entity-Zuwachs + Breaking-Change-Risiko widerspricht Anforderung 2). |
| Q2 — Scope | **Erstmal nur Labor.** Trinken/Blutdruck bleiben vorerst rein kanonisch; Schritt 4 wird so gebaut, dass Drinks/BP später ergänzt werden können, sind aber nicht Teil des aktuellen Umsetzungsschritts. |
| Q3 — Katalog-Ort | **Weiterhin `const.py`** (`LAB_MARKERS`/`LAB_DEFAULT_UNITS`/`alt_units`). Keine Verlagerung nach `entry.options` oder in eine externe Konfigurationsdatei. "Manuell erweiterbar" heißt hier: Hand-Edit im Code, über ein Release — nicht release-frei. |
| Q4 — Test-Scope | **Alle 41 Marker**, nicht nur die 22 mit echten `alt_units`. Oracle-Test deckt auch die trivialen Faktor-1-Fälle ab, damit ein künftig nachgerüsteter `alt_units`-Eintrag automatisch mitgeprüft wird. |

**Konsequenzen für §3 (Stufenplan):**

- **Schritt 3 (Nutzerentscheidung Q1) ist erledigt** — Schritt 4 ist entblockt.
- **Schritt 4, Wahl "Kombination A+B"**: Umsetzung folgt dem A-Pfad (produktiver Lese-Service/WS-Kommando für `convert_lab_display_value`-artige Konvertierung, Nicht-Ziel-Klausel aus REQ-HOM-134 wird für diesen neuen Scope widerrufen) **plus** Prüfung, ob der bestehende `reported_value`/`reported_unit`-Mechanismus bei Lab-Readings bereits ausreicht oder erweitert werden muss, um gezielt "Wert in Einheit Y abrufen" zu beantworten (nicht nur beim Schreiben protokollieren). Scope bleibt **nur Labor** (Q2) — kein neues Einheiten-Vokabular für Drinks/BP in diesem Schritt.
- **Schritt 2 (Lab-Oracle-Test)**: `specs`-Liste erweitert auf **alle 41 Marker** (Q4), nicht nur die 22 mit `alt_units` — Faktor-1-Fälle als Self-Conversion-Check mit aufnehmen.
- **Schritt 1, 5, 6, 7 unverändert** gegenüber §3.

**Reihenfolge jetzt:** Schritt 1 (Validierung) + Schritt 2 (Lab-Oracle, alle 41) + Schritt 5
(Wellbeing-Oracle) können parallel/sofort starten. Schritt 4 (Multi-Unit A+B, nur Labor) kann
jetzt ebenfalls starten (entblockt), ist aber der größte Brocken (Architektur-Impact,
`senior-developer`). Schritt 6/7 laufen begleitend.

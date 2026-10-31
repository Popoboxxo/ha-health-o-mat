# Audit: Entity-ID-Stabilität / englische object_ids — health_o_mat

- Stand: 2026-10-31, Branch `main`, HEAD `d86b247`, manifest `0.16.2`, ConfigFlow `VERSION = 2`
- Scope: ausschließlich Entity-ID-Stabilität und englisch gepinnte object_ids (kein Gesamt-Review)
- Methode: Code-Lesen + Abgleich mit HA-Core-Quelltext der Dev-Instanz (HA **2026.9.1**) + Live-Registry der Dev-Instanz (Systemsprache **de**, 328 `health_o_mat`-Entities)
- Reiner Audit: kein Anwendungscode geändert.

## 1. Mechanismus

`custom_components/health_o_mat/entity.py:34-54` — `HealthOMatEntity.suggested_object_id` überschreibt die
HA-Property. Vergleich mit HA-Core 2026.9.1 (`homeassistant/helpers/entity.py:748` und
`helpers/entity_platform.py:220-250`):

- HA-Core baut die object_id aus `platform_data.object_id_platform_translations`. Diese sind
  **seit 2026.9 in der Systemsprache**, sobald die Sprache in `NATIVE_ENTITY_IDS` steht (`de` ist enthalten) —
  sonst Englisch.
- Der Override ruft dieselbe Funktion `self._name_internal(...)`, setzt aber
  `platform_data.default_language_platform_translations` ein. Diese sind **immer Englisch**
  (`languages.DEFAULT_LANGUAGE`), d. h. der englische `strings.json`/`translations/en.json`-Wert von
  `entity.<platform>.<translation_key>.name`.
- Anschließend slugified HA den Namen (Device-Name + Entity-Name, wegen `has_entity_name = True`).
- `has_entity_name = True` wird zentral im Basis-`__init__` gesetzt (`entity.py:31`) — jede Subklasse erbt es.
- Guard `type.__getattribute__(cls, "name") is type.__getattribute__(Entity, "name")`: der Override greift nur,
  wenn keine Subklasse die `name`-Property überschreibt (identisch zum HA-Core-Guard). Keine Subklasse tut das.
- Reihenfolge in `_name_internal`: `_attr_name` gewinnt vor `translation_key`. Entities mit `_attr_name` (siehe §2)
  bekommen also den Literal-Namen als object_id-Basis — unabhängig von der Sprache, aber nicht „englisch".
- Fallback `getattr(..., "default_language_platform_translations", None) or {}`: das Attribut existiert in
  2026.9.1. Würde es fehlen (ältere HA), fiele der Override auf `{}` → `_name_internal` liefert für
  translation_key-Entities `UNDEFINED` → `super().suggested_object_id` (= HA-Default). Robust.

Randnotizen (kein Handlungsbedarf, nur Bewusstsein):

- Der Device-Class-Fallback nutzt weiterhin `self._object_id_device_class_name` (also die **object_id-Sprache**,
  bei `de` deutsch). Er greift nur, wenn eine Entity weder `_attr_name` noch einen auflösbaren
  `translation_key` hat — das trifft heute auf keine Entity zu (alle Keys vorhanden, §2c).
  Würde ein Key in `strings.json` fehlen, entstünde eine deutsche bzw. leere object_id statt einer englischen.
- Der Override nutzt die internen HA-Attribute `platform_data`, `_name_internal`,
  `default_language_platform_translations` — kein öffentliches API; bei HA-Core-Refactors bricht er still
  (Fallback = HA-Default = lokalisierte IDs bei Neuregistrierung). Ein Regressionstest gegen die Dev-Instanz
  (Registry-Check nach Erstanlage mit `language=de`) wäre die Absicherung.

**Live-Beleg (Dev-Instanz, Sprache `de`):** alle translation_key-Entities haben englische object_ids bei deutschem
`original_name`, z. B. `sensor.health_o_mat_max_drinks_today` („Heute getrunken"),
`binary_sensor.health_o_mat_max_kidney_warning` („Niere-Warnung"), `sensor.health_o_mat_max_creatinine`
(„Kreatinin"), `button.health_o_mat_max_report_awful` („Melden: Elend"). Der Mechanismus funktioniert.

## 2. Entity-Klassen je Plattform

Legende: Basis = erbt von `HealthOMatEntity` (Override vorhanden); `hen` = `has_entity_name=True` (zentral, `entity.py:31`);
TK = `_attr_translation_key`; EN = englischer Eintrag in `strings.json` `entity.<platform>.<tk>.name`.

| Datei:Zeile | Klasse | Basis | hen | TK | EN in strings.json | Ergebnis |
|---|---|---|---|---|---|---|
| sensor.py:63 | HealthOMatSensor (abstrakt) | ja | ja | — | — | Basis |
| sensor.py:81 | TodaySensor | ja | ja | `today` | ja | OK |
| sensor.py:126 | PercentSensor | ja | ja | `goal_percent` | ja | OK |
| sensor.py:145 | HistoryDrinksSensor | ja | ja | `history_drinks` | ja | OK |
| sensor.py:178 | LifetimeSensor | ja | ja | `lifetime` | ja | OK |
| sensor.py:195 | LastReadingSensor (×3) | ja | ja | `bp_{sys,dia,pulse}` (dyn., :204) | ja (3/3) | OK |
| sensor.py:233 | BloodPressureHistorySensor | ja | ja | `history_bp` | ja | OK |
| sensor.py:258 | BloodPressureCategorySensor | ja | ja | `blood_pressure_category` | ja | OK |
| sensor.py:297 | DrinksTrendSensor | ja | ja | `drinks_trend` | ja | OK |
| sensor.py:332 | BpTrendSensor | ja | ja | `bp_trend` | ja | OK |
| sensor.py:369 | GoalStreakSensor | ja | ja | `goal_streak` | ja | OK |
| sensor.py:403 | CaffeineTodaySensor | ja | ja | `caffeine_today` | ja | OK |
| sensor.py:435 | WellbeingSinceSensor | ja | ja | `wellbeing_since` | ja | OK |
| sensor.py:457 | WellbeingScoreSensor | ja | ja | `wellbeing_score` | ja | OK |
| sensor.py:495 | LabValueSensor (Katalog, 29×) | ja | ja | `lab_{marker_key}` (dyn., :520) | ja (29/29) | OK |
| sensor.py:495 | LabValueSensor (Custom) | ja | ja | `None` + **`_attr_name` = Nutzername** (:517) | n/a | **Abweichung F-2** (bewusst, §3b) |
| binary_sensor.py:45 | HealthOMatBinary (abstrakt) | ja | ja | — | — | Basis |
| binary_sensor.py:60 | GoalReachedEntity | ja | ja | `goal_reached` | ja | OK |
| binary_sensor.py:72 | BloodPressureWarningEntity | ja | ja | `bp_warning` | ja | OK |
| binary_sensor.py:92 | LabCategoryWarningEntity (9×) | ja | ja | `lab_warning_{category}` (dyn., :103) | ja (9/9) | OK |
| button.py:41 | HealthOMatButton (abstrakt) | ja | ja | — | — | Basis |
| button.py:64 | QuickDrinkButton (4×) | ja | ja | **keins**, **`_attr_name = self._label`** (:82) | n/a | **Abweichung F-1** |
| button.py:89 | CustomDrinkButton | ja | ja | `book_custom` | ja | OK |
| button.py:105 | UndoDrinkButton | ja | ja | `undo_drink` | ja | OK |
| button.py:124 | SaveReadingButton | ja | ja | `save_reading` | ja | OK |
| button.py:154 | WellbeingButton (10×) | ja | ja | `report_{key}` (dyn., :160) | ja (10/10 aus `WELLBEING_STATES`) | OK |
| number.py:52 | HealthOMatNumber (abstrakt) | ja | ja | — | — | Basis |
| number.py:69 | DailyGoalNumber | ja | ja | `daily_goal` | ja | OK |
| number.py:119 | CustomAmountNumber | ja | ja | `custom_amount` | ja | OK |
| number.py:143 | ThresholdNumber (×2) | ja | ja | `threshold_{sys,dia}` (dyn., :152) | ja (2/2) | OK |
| number.py:164 | InputNumber (×3) | ja | ja | `input_{systolic,diastolic,pulse}` (Param., :185) | ja (3/3) | OK |
| number.py:201 | WellbeingInputNumber | ja | ja | `wellbeing_input` | ja | OK |
| select.py:20 | WellbeingSelect | ja | ja | `wellbeing` | ja | OK |
| text.py:23 | FreeTextDrinkEntity | ja | ja | `freetext` | ja | OK |

Grep `_attr_name =` / `def name` / `name =`-Overrides über alle Plattformdateien: nur **button.py:82** und
**sensor.py:517**. Keine `name`-Property-Overrides.

**strings.json-Abgleich:** Alle in Code verwendeten Translation-Keys (statisch + dynamisch generiert) existieren in
`strings.json`, `translations/en.json` und `translations/de.json` — die drei `entity`-Bäume sind keyidentisch,
kein Key fehlt, keine verwaisten Keys gefunden.

**Zählung:** 30 Klassen (davon 5 abstrakte Basen) → **25 konkrete Klassen, 23 voll konform**,
2 mit Literal-Namen (QuickDrinkButton vollständig; LabValueSensor nur im Custom-Pfad).

### F-1 QuickDrinkButton (button.py:64-82) — Literal-Name, deutsche object_ids

- `_attr_name = self._label`, Label kommt aus `entry.options["quick_drinks"]` bzw. `DEFAULT_QUICK_DRINKS`
  (`const.py:57-62`), dessen Defaults **deutsch** sind („Glas Wasser", „Flasche Wasser", „Tasse Kaffee", „Glas Saft").
- Folge (live belegt): `button.health_o_mat_max_glas_wasser`, `…_flasche_wasser`, `…_tasse_kaffee`, `…_glas_saft`.
- **Nicht sprachabhängig** (die ID wechselt nicht mit der Systemsprache) — also nicht die Fehlerklasse
  „localized object_id". Aber **nicht englisch** und damit regelwidrig gegen „absolut verboten: hartcodiertes
  `_attr_name`" aus `integration-development.md` (der Code-Kommentar M-8 begründet die Ausnahme).
- Stabilität ist gegeben: unique_id = `{entry_id}_button_quick_{index}` (slot-index-basiert), die entity_id bleibt
  nach Erstregistrierung in der Registry fixiert, auch wenn das Label geändert wird
  (live: `button.health_o_mat_e2e_deep_tasse_kaffee` hat `original_name` „Kaffee").
- Nebenbefund: Bei englischer Systemsprache entstünden dieselben deutschen IDs, weil der Default-Text deutsch
  ist und nicht übersetzt wird; ein englischsprachiger Nutzer bekäme deutsche Button-Namen *und* IDs.

## 3. Dynamische Laborwert-Entities (REQ-HOM-122+)

### 3a. Katalog-Marker und Kategorie-Warnungen — konform

- `LAB_MARKERS` (`const.py:192ff`): 29 Marker → `LabValueSensor` mit TK `lab_{marker_key}` (`sensor.py:520`).
  Abgleich per AST-Parse von `const.py` gegen `strings.json`: **29/29 Keys vorhanden**.
- `LAB_CATEGORIES` (`const.py:175-186`): 10 Kategorien, davon `other` bewusst ohne Warn-Entity
  (`binary_sensor.py:31-40`). → `LabCategoryWarningEntity` mit TK `lab_warning_{category}`; **9/9 Keys vorhanden**.
  Das Set wird zur Laufzeit aus `effective_lab_markers()` abgeleitet; eine Custom-Marker-Kategorie kann laut
  Normalisierung beliebig sein (`logic.py:1022`: `category = item.get("category") or "other"`) — siehe F-3.
- unique_ids: `{entry_id}_lab_{marker_key}` bzw. `{entry_id}_binary_lab_warning_{category}` — keyed auf
  stabile Katalog-Schlüssel, nicht auf Namen.
- Live (de): `sensor.health_o_mat_max_creatinine`, `…_total_cholesterol`, `binary_sensor.…_liver_warning` usw.
- Kosmetik (kein Bruch, nicht migrieren): EN-Namen „ALT (ALT/GPT)" / „AST (AST/GOT)" erzeugen
  `…_alt_alt_gpt` / `…_ast_ast_got`. Bereits registriert → Umbenennen wäre ein Breaking Change ohne Nutzen.

### 3b. Custom-Marker — echte, bewusst eingegangene Spannung (F-2)

Codepfad: Nutzer-Options (`ws_api.py:1876-1883` → `logic.normalize_lab_custom_markers`, `logic.py:994-1044`)
→ `effective_lab_markers` (`logic.py:1047`, `is_custom: True`, `name` = Nutzertext) → `LabValueSensor.__init__`
(`sensor.py:514-518`): `_attr_name = marker_def["name"]`, `_attr_translation_key = None`.

- Es gibt keinen Config-Flow-Pfad; Custom-Marker kommen ausschließlich über die WS-API/Panel in `entry.options`.
- **Der translation_key-/Pinning-Pfad wird by design umgangen.** Der Override läuft zwar, `_name_internal`
  liefert aber `_attr_name` → object_id = HA-slugify(Device-Name + Nutzername), z. B. „Vitamin D" →
  `sensor.health_o_mat_<person>_vitamin_d`, „Ferritin gesamt" → `…_ferritin_gesamt`.
- Spannung, explizit: Die Regel „object_id immer englisch" ist für frei gewählte Namen **nicht erfüllbar** —
  es gibt keinen englischen Quelltext. Erfüllt bleibt aber die eigentlich schützende Eigenschaft:
  **sprachunabhängig** (die ID hängt nicht von der Systemsprache ab) und **nach Erstregistrierung stabil**
  (Registry fixiert die entity_id; Umbenennen des Markers ändert nur `original_name`).
  Ob „englisch" hier zu „sprachunabhängig + stabil" aufgeweicht werden darf, ist eine **Produktentscheidung**,
  keine technische — offen für den Nutzer.
- **Echte Stabilitätslücke (unique_id!), relevanter als die Sprachfrage:** Der Marker-`key` (→ unique_id
  `{entry_id}_lab_{key}`) wird aus `item["key"]` übernommen, sonst aus dem Namens-Slug gebildet, bei Kollision
  mit `_2`/`_3` suffixiert **in Listenreihenfolge** (`logic.py:1014-1019`). Da `normalize_lab_custom_markers`
  das Ergebnis inkl. `key` zurück in die Options schreibt (`ws_api.py:1883`), ist der Key nach dem ersten
  Speichern persistiert und stabil — **sofern das Panel den `key` beim erneuten Speichern mitschickt**.
  Schickt der Client eine Liste ohne `key` (z. B. Neuanlage, oder ein Client, der `key` verwirft), wird neu
  geslugt: Umbenennen „Vitamin D" → „Vitamin D3" würde dann den Key und damit die **unique_id ändern**
  (neue Entity, alte verwaist, Messwerte unter altem `marker_key` im Store nicht mehr zugeordnet), und das
  Löschen eines früheren Duplikats verschiebt `_2` → Basis-Key. Nicht live verifiziert (keine Custom-Marker in
  der Dev-Registry). **Panel-Prüfung (`www/health-o-mat-panel.js:2079-2112, 1166-1191`):** Das Panel bietet nur
  Hinzufügen/Entfernen, kein Umbenennen; neue Marker werden als `{name, unit, category}` ohne `key` angehängt,
  bestehende Einträge werden aus den (server-normalisierten, `key`-haltigen) Settings unverändert
  durchgereicht. → Über die offizielle UI ist der Key nach dem ersten Speichern stabil; Risiko besteht nur
  für Fremd-Clients/WS-Aufrufe, die eine Liste ohne `key` senden. Server-seitig ist das nicht abgesichert
  (Härtungsvorschlag in §5, nicht-breaking).
- Slugify-Asymmetrie: `logic._slugify_lab_marker_name` (ASCII-only, „Hämoglobin" → `h_moglobin`) ≠
  HA-slugify für die object_id (Transliteration, `haemoglobin`/`hamoglobin`). Kein Stabilitätsproblem, aber
  unique_id-Suffix und entity_id-Suffix sehen unterschiedlich aus.

### F-3 Custom-Kategorie ohne Translation-Key (latent)

`normalize_lab_custom_markers` akzeptiert beliebige `category`-Strings. Liefert ein Client eine Kategorie
außerhalb von `LAB_CATEGORIES` (z. B. `vitamins`), erzeugt `binary_sensor.py:36-41` eine
`LabCategoryWarningEntity` mit TK `lab_warning_vitamins`, für den **kein** `strings.json`-Eintrag existiert.
Dann greift im Override der Device-Class-Fallback (`PROBLEM` → object_id-Sprache, bei `de` „Problem")
→ object_id wäre z. B. `binary_sensor.<device>_problem` (lokalisiert, kollisionsanfällig). Ob die WS-API die
Kategorie gegen `LAB_CATEGORIES` validiert, wurde im normalize-Pfad **nicht** gefunden (dort nur `strip()`);
das Panel schickt den Wert eines Kategorie-Feldes (`lab-custom-category`, Default `other`) — über die UI
also nur Katalog-Kategorien; Fremd-Clients können beliebige Strings setzen. Latent, nicht live aufgetreten.

Testabdeckung: `tests/test_translations.py:457-475` prüft bereits, dass für **jeden** `LAB_MARKERS`-Key ein
`entity.sensor.lab_<key>`-Eintrag existiert (inkl. Namensgleichheit mit `name_de`/`name_en`) — der dynamische
Katalog ist also gegen Drift abgesichert. Keine vergleichbare Code-seitige Absicherung gefunden für
`LAB_CATEGORIES` → `lab_warning_*` und `WELLBEING_STATES` → `report_*` (heute vollständig, aber ungeschützt).

## 4. Vergleich mit ha-go-gauge

Quelle: `https://github.com/Popoboxxo/ha-go-gauge`, Shallow-Clone von `main` @ `b8b2cbc` (2026-10-27),
gelesen, nichts ausgeführt; manifest `2.1.1`, ConfigFlow-Migrationen bis v8. Domain `go_gauge`.

**Ergebnis klar: ha-go-gauge hat KEINEN `suggested_object_id`-Override und keinen äquivalenten
Pinning-Mechanismus.** Volltextsuche nach `suggested_object_id` / `default_language_platform_translations` im
Code: 0 Treffer. Die Annahme, das Problem sei dort „richtig gelöst" und health_o_mat müsse nachziehen, trifft
nicht zu — es ist umgekehrt: **health_o_mat ist beim Pinning weiter.**

Was go_gauge tatsächlich macht:

| Aspekt | ha-go-gauge | ha-health-o-mat |
|---|---|---|
| `has_entity_name` + `translation_key`, kein `_attr_name` | ja, durchgängig (`entity.py:45,79`; alle Plattformen) | ja, bis auf F-1/F-2 (bewusste Literal-Namen) |
| object_id bei Neuregistrierung unter HA ≥ 2026.9 + `de` | **lokalisiert** (deutsch) — README §„Entity names and entity IDs" dokumentiert das explizit als akzeptiert, Beispiel `binary_sensor.go_gauge_konto_api_erreichbar` | **englisch** (Override, live belegt) |
| Entscheidung dazu | `docs/E2E-v7-entity-id-migration-2026-09-12.md:338,366`: Option „englisches `suggested_object_id` erzwingen" als offene Entscheidung **ND-1** notiert, nicht umgesetzt | umgesetzt |
| Device-Name im entity_id-Präfix | Konto-Device hart „Go Gauge Konto" (deutsch) → `go_gauge_konto_*` | „Health-O-Mat {person}" (sprachneutral) |
| Einmalige Altbestands-Migration DE→EN | **ja**: ConfigFlow v6 (`original_name` via `ENTITY_NAME_MIGRATION`, `const.py:210-248`) und v7 (`new_entity_id` via `ENTITY_ID_MIGRATION`-Slug-Tabelle, `const.py:250-395`; `__init__.py:60-160`) | nicht nötig gewesen (Pinning vor dem Problem) |

Was health_o_mat von go_gauge **übernehmen** sollte (nur relevant, falls §5 eine Registry-Migration auslöst):

1. **Kollisionsprüfung vor `new_entity_id`** (`__init__.py` `_make_entity_id_migration_callback`): Ziel-ID nur
   setzen, wenn `registry.async_get(target) is None and hass.states.async_available(target)`; sonst überspringen
   + Warnung mit Paarliste. Verhindert, dass ein `ValueError` den ganzen Pass abbricht.
2. **Version nur bei erfolgreichem Pass anheben** (v7: `_async_migrate_entity_ids` liefert `bool`); bei Fehler
   bleibt `entry.version` stehen → HA versucht es beim nächsten Start erneut.
3. **Atomarer Abschluss**: data/options/version in **einem** `async_update_entry`-Aufruf (go_gauge-Kommentar:
   direkte `entry.version = N`-Zuweisung wirft seit HA 2026.9). health_o_mat macht das bereits so.
4. **Migrationslogik HA-frei** (reine Funktionen in `const.py`, unit-testbar) — passt zur Projektregel
   „Logik in HA-freie Module".

Was health_o_mat **nicht** übernehmen sollte:

- Die **Slug-Tabelle** (`ENTITY_ID_MIGRATION`, String-Ersetzung auf object_ids mit Positions-Ankern,
  Dedup-Suffix-Handling): fragil, sprach- und gerätenamenabhängig. health_o_mat kann Ziel-IDs
  deterministisch aus der **unique_id** ableiten (`{entry_id}_<key>` → Key ist bekannt) — robuster.
- Das Akzeptieren lokalisierter IDs (README-Linie von go_gauge): würde die bestehende, funktionierende
  Garantie von health_o_mat aufgeben.

**Empfehlung an go_gauge (außerhalb dieses Scopes, nur Hinweis):** ND-1 mit dem health_o_mat-Override
(`entity.py:34-54`) lösen — dann sind Neuregistrierungen englisch; der vorhandene v7-Pass deckt den Altbestand.

## 5. Korrektur-/Migrationsvorschlag (nicht implementiert)

### Gesamturteil

- **Keine Registry-Migration erforderlich, um die bestehende Garantie herzustellen.** Alle 23 konformen
  Klassen (inkl. 29 Katalog-Marker, 9 Kategorie-Warnungen, 10 Wellbeing-Buttons) erzeugen nachweislich
  englische, sprachunabhängige object_ids; keine `strings.json`-Lücke.
- Die zwei Abweichungen (F-1 Quick-Drink-Buttons, F-2 Custom-Marker) sind **sprachunabhängig und stabil**,
  aber **nicht englisch**, weil der Name Nutzertext bzw. deutscher Default-Text ist. Ob das ein Defekt ist,
  ist eine **Produktentscheidung** (Regel „immer englisch" vs. Spec „Nutzer wählt Namen").

### A. Nicht-breaking (reine Code-Fixes, kein Registry-Eingriff, PATCH/MINOR)

| ID | Maßnahme | Betrifft |
|---|---|---|
| A-1 | Server-seitige Validierung der Custom-Marker-`category` gegen `LAB_CATEGORIES`, Fallback `other` (in `logic.normalize_lab_custom_markers`) | F-3 |
| A-2 | Key-Erhalt server-seitig: eingehende Einträge ohne `key`, deren `name` einem bereits gespeicherten Marker entspricht, erben dessen `key` (statt Neu-Slug + Suffix) — schützt unique_id gegen Fremd-Clients | F-2 (unique_id-Stabilität) |
| A-3 | Unit-Test analog `test_translations.py:457`: jeder `LAB_CATEGORIES`-Key (≠ `other`) → `binary_sensor.lab_warning_<key>`, jeder `WELLBEING_STATES`-Key → `button.report_<key>` existiert in `strings.json`/`en`/`de` | Drift-Schutz |
| A-4 | E2E-Regression (Dev-Instanz, Sprache `de`): nach Erstanlage einer Test-Person prüfen, dass alle translation_key-Entities englische object_ids haben (Registry `config/entity_registry/list`) — fängt einen stillen Bruch des Overrides durch HA-Core-Refactors (`platform_data`/`_name_internal` sind internes API) | Mechanismus |
| A-5 | **Nur für Neuregistrierungen** englisch/slot-basiert pinnen: in `QuickDrinkButton` `suggested_object_id` → `quick_drink_<n>`, in Custom-`LabValueSensor` → `lab_<key>`; `_attr_name` (Anzeige) bleibt Nutzertext. Bestehende Registry-Einträge behalten ihre entity_id (HA ändert registrierte IDs nie) → **nicht breaking**. Nebenwirkung: Bestands- und Neuinstallationen haben unterschiedliche ID-Schemata, bis ggf. B-1 läuft | F-1, F-2 |
| A-6 | (optional, Produkt) `DEFAULT_QUICK_DRINKS`-Labels übersetzbar machen (nur Anzeigename) | F-1 |

### B. Breaking (Registry-Migration) — nur falls der Nutzer „ausnahmslos englisch auch im Bestand" entscheidet

Nach `.claude/rules/integration-development.md` „Entity-Registry-Migration bei Umbenennung":

- **B-1 Umfang:** ausschließlich `button.*` mit unique_id `{entry_id}_button_quick_{n}` (live 4 je Person;
  aktuell `…_glas_wasser`, `…_flasche_wasser`, `…_tasse_kaffee`, `…_glas_saft`) und Custom-`sensor.*` mit
  unique_id `{entry_id}_lab_{key}` wo `key ∉ LAB_MARKERS`. Ziel: `button.<device_slug>_quick_drink_<n+1>` bzw.
  `sensor.<device_slug>_lab_<key>`. **Keine** anderen Entities (bereits englisch).
- **unique_id wird NIE geändert**; geändert wird nur `entity_id` (`new_entity_id`). `original_name` nicht
  anfassen (Anzeige bleibt Nutzertext).
- Umsetzung: `config_flow.py` `VERSION = 2 → 3`; in `__init__.async_migrate_entry` Stufe `entry.version < 3`
  mit `er.async_migrate_entries(hass, entry.entry_id, callback)`. Callback leitet das Ziel **aus der unique_id**
  ab (nicht aus dem Slug, Lehre aus go_gauge), Device-Slug aus dem aktuellen entity_id-Präfix bzw.
  `slugify(device.name)`; Kollisionsprüfung + Skip-Warnung (go_gauge-Punkt 1); Version nur bei Erfolg
  anheben (go_gauge-Punkt 2); Downgrade-Guard `entry.version > 2` → `> 3` mitziehen.
- Custom-Marker: der Ziel-Suffix `lab_<key>` ist zwar stabil, aber **ebenfalls nicht englisch** (Key = Slug des
  Nutzernamens). B-1 kann die Spannung aus §3b also nicht auflösen, nur vereinheitlichen — das ist bei der
  Entscheidung zu berücksichtigen.
- Release: **MAJOR** (`0.16.2` → `1.0.0`; entity_id-Änderung ist laut Regel immer breaking), echtes
  GitHub-Release mit 💥-Eintrag: „Quick-Drink-Buttons und eigene Laborwert-Marker erhalten neue,
  sprachunabhängige Entity-IDs (`…_quick_drink_1` … / `…_lab_<key>`). Automationen, Skripte und Dashboards,
  die die alten IDs (`…_glas_wasser` usw.) nutzen, müssen angepasst werden. Verlauf bleibt erhalten
  (unique_id unverändert)."
- Post-Release (Workflow-Schritt 7): HACS-Update-Test von 0.16.2 auf der Dev-Instanz, Registry prüfen;
  verwaiste Alt-Entities sind bei reiner `new_entity_id`-Umbenennung nicht zu erwarten.

### Empfehlung

A-1 bis A-4 umsetzen (nicht-breaking, schließen echte Lücken). A-5 nur nach Produktentscheidung.
B-1 **nicht** empfehlen: hoher Bruch für Bestandsnutzer (Automationen auf Quick-Drink-Buttons sind der
typische Use-Case) bei geringem Nutzen — die schützende Eigenschaft (Sprachunabhängigkeit + Stabilität) ist
bereits erfüllt.

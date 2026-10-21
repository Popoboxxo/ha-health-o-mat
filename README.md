# HA Health-O-Mat

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![Validate](https://github.com/Popoboxxo/ha-health-o-mat/actions/workflows/validate.yml/badge.svg)

**Trinken & Blutdruck im Blick** — das Gesundheits-Tagebuch für Home Assistant.
Lokal, dauerhaft gespeichert (überlebt jeden Recorder-Purge), alles als native
Entities verfügbar und jederzeit als Excel-taugliche CSV exportierbar.

> ⚠️ Keine medizinische Beratung — Klassifikationen/Warnungen dienen nur der Orientierung.

## Features

- 💧 **Getränke-Tracking**: „Wie viel habe ich heute getrunken?" — sauberer mL-Sensor,
  Prozent-Gauge, Breakdown nach Getränketyp
- 🔘 **Quick-Drink-Buttons** (Glas Wasser 200 · Flasche 500 · Kaffee 250 · Saft 200)
  + Custom-Menge + **Freitextfeld** mit Parser: `Kaffee 300ml`, `0,5 l wasser`,
  `cola`, `Ingwertee 400` — alles funktioniert
- 🩺 **Blutdruck**: Eingabefelder (sys/dia/puls) + Speichern-Button, Verlaufs-Sensoren,
  7-Tage-Mittelwert, konfigurierbare Warnschwelle (Default 140/90)
- 📈 **Abgeleitete Metriken**: WHO-Blutdruck-Kategorie, Trink-Trend (± % vs.
  Vorwochen-Ø), Blutdruck-Trend, Ziel-Serie (Streak), **geschätztes** Koffein
  heute und der **Wohlbefinden-Score (1–5)** — je eine Entity für den
  Entscheidungswert, Details als Attribute
- ↩️ **Undo-Button** für die letzte Buchung
- 📄 **CSV-Export** per Service → `/config/health_o_mat_export/`
  (Semikolon + UTF-8-BOM = Excel-Doppelklick-tauglich)
- 👥 **Multi-Person**: ein Config-Entry = eine Person = ein Device — beliebig viele
- 🌙 **Tagesgrenze**: einstellbare Reset-Uhrzeit (Options, 0–23 Uhr, Default 0 Uhr);
  neustartfest, weil „heute"/„gestern" on-read aus der Historie berechnet werden
  (kein Reset-Job, DST-fest)
- 🗄️ **Optionale Aufbewahrung**: Historie älter als X Monate wandert beim Start ins
  Archiv (Options „Aufbewahrung", Default aus); Summen/Lebenszähler bleiben
  unverändert, der CSV-Export umfasst das Archiv

## Installation (HACS)

1. HACS → Custom Repositories → `Popoboxxo/ha-health-o-mat` (Kategorie: Integration)
2. Herunterladen, HA neu starten
3. Einstellungen → Geräte & Dienste → Integration hinzufügen → **HA Health-O-Mat**
4. Person anlegen (pro Person einmal durchlaufen)

## Entities & Benennung (je Person)

**Sprechende englische IDs, lokalisierte Anzeigenamen:** Die Entity-IDs sind
sprachunabhängig auf Englisch und entstehen aus dem englischen Anzeigenamen
(`sensor.health_o_mat_max_drinks_today`), der angezeigte Name folgt der
System-/Profilsprache von Home Assistant (de/en). Pro Person/Device lautet
das ID-Muster:

```
<platform>.health_o_mat_<person-slug>_<name-suffix>
z. B.  sensor.health_o_mat_caro_drinks_today
```

Die Integration **pinnt die Entity-ID-Suffixe auf Englisch** — unabhängig von
der Systemsprache. Das ist wichtig, weil Home Assistant seit 2026.9 für
viele Sprachen (u. a. Deutsch) Entity-IDs in der Systemsprache erzeugt
(„native entity IDs"): Ohne Pinning würde aus „Melden: Sehr schlecht" ein
`button.…_melden_sehr_schlecht`, das mit jedem Sprachwechsel wechseln würde.

| Typ | Entity-ID (Suffix) | Anzeige (de/en) | Zweck |
|---|---|---|---|
| sensor | `drinks_today` | Heute getrunken / Drinks today | **mL heute** (+ count, %, breakdown, gestern) |
| sensor | `daily_goal_progress` | Tagesziel-Fortschritt / Daily goal progress | Gauge-fähig |
| sensor | `drinks_history` | Getränke-Historie / Drinks history | letzte 100 Buchungen als JSON + Gesamtzahl |
| sensor | `lifetime_total` | Gesamtmenge / Lifetime total | kumuliert |
| sensor | `blood_pressure_systolic` / `blood_pressure_diastolic` / `pulse` | Blutdruck systolisch / diastolisch, Puls | letzte Messung (measurement → Graph) |
| sensor | `blood_pressure_history` | Blutdruck-Historie / Blood pressure history | letzte 30 Messungen als JSON |
| sensor | `wellbeing_last_reported` | Wohlbefinden zuletzt gemeldet / Wellbeing last reported | Zeitstempel |
| sensor | `wellbeing_score` | Wohlbefinden-Score / Wellbeing score | numerisches Wohlbefinden 1–5 (rein abgeleitet) |
| sensor | `blood_pressure_category` | Blutdruck-Kategorie / Blood pressure category | WHO-Kategorie der letzten Messung (optimal … hypertensive Krise) |
| sensor | `drinks_trend` | Trink-Trend / Drinks trend | ± % heute vs. Vorwochen-Ø (mL) |
| sensor | `blood_pressure_trend` | Blutdruck-Trend / Blood pressure trend | steigend/fallend/stabil aus 7-Tage-Mitteln |
| sensor | `goal_streak` | Ziel-Serie / Goal streak | Tage in Folge mit erreichtem Tagesziel (+ Bestwert) |
| sensor | `caffeine_today` | Koffein heute / Caffeine today | **geschätzte** mg Koffein heute |
| binary_sensor | `daily_goal_reached` / `blood_pressure_warning` | Tagesziel erreicht, Blutdruck-Warnung | Status |
| button | Quick-Drinks (Label aus der Konfiguration), `book_custom_amount`, `undo_last_drink`, `save_measurement` | Buchen/Löschen/Speichern | Alltagseingabe |
| button | `report_very_bad` … `report_great` | Melden: … / Report: … | Wohlbefinden |
| select | `wellbeing` | Wohlbefinden / Wellbeing | Optionen werden ebenfalls übersetzt |
| text | `log_drink_free_text` | Getränk buchen (Freitext) | „Kaffee 300ml" → Enter = buchen |
| number | `daily_goal`, `custom_drink_amount`, `systolic/diastolic_warning_threshold`, `new_reading_*` | Tagesziel (mL), Eigenmenge (mL), Warnschwellen, BP-Eingabe | Runtime-Einstellungen |

### Entities im Detail

**Sensoren**

- `sensor.…_drinks_today` — getrunkene Menge des heutigen Tagesfensters in mL
  (`device_class: volume`, `state_class: total` mit `last_reset` = Beginn des
  laufenden Tagesfensters). Attribute: `drinks_count` (Buchungen heute),
  `percent_of_goal` (Fortschritt), `breakdown_by_type` (JSON: mL je Getränketyp),
  `last_drink_at`, `yesterday_ml` (Vortag, gleiche Tagesgrenze).
- `sensor.…_daily_goal_progress` — Prozent des Tagesziels (0–100), für
  Gauge-/Bar-Karten; `state_class: measurement` → Verlaufsgraph.
- `sensor.…_drinks_history` — Zustand = Anzahl Buchungen heute; Attribut
  `entries_json` = die **letzten 100** Buchungen als JSON (Zeitstempel, mL, Typ,
  Quelle) und `total_count` = Gesamtzahl aller Buchungen. Der Cap hält das
  State-Objekt/den Recorder klein; der Vollbestand bleibt im Store und im
  CSV-Export. Für Automatisierungen und Backup-Zwecke.
- `sensor.…_lifetime_total` — kumulierte Gesamtmenge in mL seit Start
  (`device_class: volume`, `state_class: total_increasing` → Langzeitstatistik
  ohne Zähler-Rücksetzungen). Startwert beim Integration-Setup eintragbar (z. B.
  Migration vom alten Wasser-Zähler).
- `sensor.…_blood_pressure_systolic` / `_diastolic` / `_pulse` — die letzte
  gemessene Messung (sys/dia mmHg mit `device_class: pressure`, Puls BPM,
  `state_class: measurement` → HA-Historie zeichnet automatisch auf). Attribute:
  `measured_at`, `avg_7d` (Mittelwert über ein echtes rollierendes
  7-Tage-Fenster), `readings_total`.
- `sensor.…_blood_pressure_history` — Zustand = Gesamtzahl der Messungen;
  Attribut `history_json` = die letzten 30 Messungen als JSON.
- `sensor.…_wellbeing_last_reported` — Zeitstempel der letzten
  Wohlbefinden-Meldung (`device_class: timestamp`).

**Abgeleitete Metriken**

- `sensor.…_blood_pressure_category` — WHO-Kategorie der letzten Messung
  (`optimal`, `normal`, `high_normal`, `grade_1`, `grade_2`, `grade_3`,
  `crisis`; de/en übersetzt). Es zählt die höhere der beiden Achsen (sys/dia);
  die hypertensive Krise greift bei sys > 180 **und** dia > 120. Ohne Messung →
  `unknown`. Attribute: `measured_at`, `systolic`, `diastolic`.
- `sensor.…_drinks_trend` — Prozentänderung der heutigen Menge gegenüber dem
  Tages-Ø der sieben vollständigen Vorwochentage (`%`, `state_class: measurement`;
  das Ø wird immer durch 7 geteilt, buchungsfreie Tage zählen als 0). Ohne
  Vorwochendaten (Ø = 0) → `unknown`. Attribute: `today_ml`, `prev_week_avg_ml`.
- `sensor.…_blood_pressure_trend` — Richtung des Blutdrucks aus zwei
  aneinandergrenzenden 7-Tage-Mitteln (`rising` / `falling` / `stable`, de/en
  übersetzt); „stabil" unter 2 mmHg Delta. Weniger als 3 gültige Messungen
  (sys **und** dia) → `unknown`. Attribute: `sys_delta`, `dia_delta`,
  `sys_avg_recent`, `sys_avg_previous`.
- `sensor.…_goal_streak` — Anzahl Tage in Folge mit erreichtem Tagesziel
  (on-read, dieselbe Tagesgrenze wie „heute"; der laufende Tag zählt nur mit,
  wenn das Ziel bereits erreicht ist). Einheit Tage (`d`). Attribut
  `best_streak` = längste Serie der gesamten Historie.
- `sensor.…_caffeine_today` — **grobe Schätzung** der Koffeinzufuhr des
  laufenden Tages in mg (`state_class: measurement`) anhand einer mg/100-mL-Tabelle
  je Getränketyp (`const.py`); unbekannte Typen und „Eigen" zählen als 0 mg.
  Attribut `caffeine_by_type_mg` = JSON mit mg je koffeinhaltigem Getränketyp.
  Reale Werte schwanken stark — **keine medizinische Aussage**.
- `sensor.…_wellbeing_score` — **numerische Darstellung des Wohlbefindens auf
  der Skala 1 … 5**: 1 = „Sehr schlecht" (schlechtester Wert) … 5 = „Super"
  (bester Wert). Die Skala ist **reihenfolgetreu aus den fünf Wohlbefinden-
  Zuständen abgeleitet** (Position in der Zustandsliste + 1) — kein fest
  verdrahteter Zahlenblock; kommt ein neuer Zustand hinzu, wächst die Skala
  automatisch mit. `state_class: measurement` (→ HA-Statistik/Graph nutzbar),
  **ohne Einheit und ohne `device_class`** (der Score ist dimensionslos). Ohne
  Meldung ist der Zustand `unknown` — **nie 0** (0 wäre der schlechteste Wert
  und würde den Verlauf verfälschen). Attribute: `reported_at` (Zeitpunkt der
  Meldung) und `scale_max` (5). Der Wert ist **rein abgeleitet** — siehe
  „Wohlbefinden-Score: die Skala 1 … 5" unten.

**Wohlbefinden-Score: die Skala 1 … 5**

| Score | Wohlbefinden-Zustand |
|---|---|
| 1 | Sehr schlecht (schlechtester Wert) |
| 2 | Schlecht |
| 3 | Okay |
| 4 | Gut |
| 5 | Super (bester Wert) |

Die Zuordnung ist **reihenfolgetreu** aus den fünf Wohlbefinden-Zuständen
abgeleitet (Index + 1) und **wächst automatisch mit**, wenn ein neuer Zustand
hinzukommt — Score und Attribut `scale_max` stammen aus derselben Quelle und
können deshalb nicht auseinanderlaufen.

> ℹ️ Der Score ist **rein abgeleitet**: Es gibt **keine eigene Datenhaltung**
> (kein eigener Store, keine Migration des Datenbestands). Der Wert wird
> jederzeit on-read aus der letzten Wohlbefinden-Meldung berechnet und ist zu
> 100 % an die Rohdaten gekoppelt — wird die Rohmeldung geändert oder gelöscht,
> ändert sich der Score automatisch mit.

**Binary-Sensoren**

- `binary_sensor.…_daily_goal_reached` — `on`, sobald das Tagesziel erreicht
  ist (ideal für Benachrichtigungen: „triggern auf on").
- `binary_sensor.…_blood_pressure_warning` — `on`, wenn die letzte Messung
  über den konfigurierbaren Warnschwellen liegt (Defaults 140/90 mmHg,
  änderbar über die Number-Entities `…_systolic_warning_threshold` /
  `…_diastolic_warning_threshold`).

**Buttons**

- **Quick-Drinks** — je konfiguriertem Quick-Drink ein Button (Label, mL und
  Icon kommen aus der Integration-Konfiguration; der Button-Name ist daher
  nutzerdefiniert, z. B. `button.…_glas_wasser`).
- `button.…_book_custom_amount` — bucht die unter `number.…_custom_drink_amount`
  eingetragene Menge.
- `button.…_undo_last_drink` — entfernt die letzte Getränkebuchung.
- `button.…_save_measurement` — übernimmt die drei Number-Eingaben
  (`new_reading_systolic/diastolic/pulse`) als neue Blutdruckmessung und leert
  die Eingabefelder.
- `button.…_report_very_bad` … `report_great` — Wohlbefinden-Meldung: setzt
  den Select auf den Status und den Zeitstempel-Sensor.

**Select: kontinuierlicher Gesundheitszustand**

- `select.…_wellbeing` — „Wohlbefinden" mit 5 Stufen (Sehr schlecht → Super).
  Das ist die kontinuierliche Darstellung des Gesundheitszustands: Der
  HA-Verlaufsgraph zeigt ihn als Balken-/Timeline-Darstellung, mushroom
  bietet `custom:mushroom-select-card`. Attribute: `emoji`, `reported_at`,
  `history_json` (letzte 10 Meldungen). Service-Aufrufe nutzen die Roh-Keys
  (`very_bad`, `bad`, `okay`, `good`, `great`).

**Text: Freitext-Buchung**

- `text.…_log_drink_free_text` — Freitexteingabe wie „Kaffee 300ml",
  „0,5 l wasser", „cola", „Ingwertee 400", „350". Der Parser zieht die Menge
  per Regex (ml/mL/l, auch Dezimal mit Komma/Punkt) und ordnet die restlichen
  Wörter über ein Lexikon (Default: wasser/water, kaffee/coffee, tee/tea,
  bier/beer, wein/wine, milch/milk, cola, limo, saft/juice, sekt …) einem
  Getränketyp zu; unbekannte Typen werden wörtlich übernommen. Das Lexikon ist
  über den Options-Dialog vollständig anpassbar (Schritt „Getränke-Lexikon",
  ein Wort/Zeile im Format `wort=Typ,ml`).
  **Gespeichert wird nur das strukturierte Ergebnis** (Zeitstempel, `ml`, Typ,
  Quelle `freetext`) — der Rohtext landet **nicht** in der Historie; er bleibt
  kurzlebig in den Entity-Attributen (`last_input`, `drink_type`,
  `amount_ml`) und wird beim nächsten Setzen überschrieben. Nicht erkennbare
  Eingaben erzeugen einen Entity-Fehler mit Lösungsbeispielen, statt
  stillschweigend etwas zu buchen.

**Numbers (Laufzeit-Einstellungen)**

- `number.…_daily_goal` — Tagesziel in mL (sofort wirksam, persistiert via
  Options-Flow).
- `number.…_custom_drink_amount` — Eigenmenge in mL für den
  „Eigenen Betrag buchen"-Button.
- `number.…_systolic_warning_threshold` / `_diastolic_warning_threshold` —
  Warnschwellen für den Blutdruck-Warn-Binary-Sensor.
- `number.…_new_reading_systolic` / `_diastolic` / `_pulse` — Eingabefelder
  für die nächste Blutdruckmessung (mit `save_measurement`-Button übernehmen).

Die beiden Mengen-Entities melden die Einheit **mL** — die HA-kanonische
Schreibweise, konsistent zu den Volumen-Sensoren (`device_class: volume`).
Intern bleiben die Datenfeld-Namen unverändert: `daily_goal_ml` (Tagesziel,
persistiert in den Config-Entry-Options) und `custom_amount_ml` (Eigenmenge,
Runtime-Speicher) — das sind Datenfelder, keine Einheiten.

### Migration (Entity-IDs & Konfiguration)

- **Update von v0.2.0 oder älter:** betroffene Entities registrieren sich
  beim ersten Start **neu mit englischen IDs**; alte Registry-Einträge
  erscheinen verwaist und können gelöscht werden.
- **Update von v0.3.0 auf einem deutschen HA:** v0.3.0 hatte noch keine
  Englisch-Pinning — dort können Entity-IDs in Deutsch erzeugt worden sein
  (z. B. `…_melden_sehr_schlecht`). Ab v0.4.0 werden neue Registrierungen
  immer englisch benannt. Um bestehende deutsche IDs zu ersetzen: alle
  health-o-mat-Entities der Person im Entity-Registry löschen (Einstellungen
  → Geräte & Dienste → Device → Entitäten löschen) und HA neu starten — die
  Entities kommen mit englischen IDs zurück. Getränke-/Messdaten bleiben
  erhalten (sie hängen am Config-Entry, nicht an der Entity-ID).
- **Update auf v0.5.0 (Quick-Drinks nach Options):** Quick-Drink-Buttons sind
  jetzt über den Options-Dialog der Integration editierbar (vorher fest in der
  Einrichtung verankert). Die Migration läuft beim Start automatisch
  (Config-Entry v1 → v2) — bestehende Buttons und Daten bleiben unverändert.
- **Update auf v0.6.0 (Getränke-Lexikon + Reset-Uhrzeit nach Options):** zwei
  neue Options-Schritte (Getränke-Lexikon, Reset-Uhrzeit im Schritt „Tagesziel
  & mehr"). Keine Breaking Changes, keine Migration nötig — beide Optionen
  haben sinnvolle Defaults (eingebautes Lexikon, Reset-Uhrzeit 0 Uhr) und
  wirken sich erst nach expliziter Änderung im Options-Dialog aus.
- **Optionale Aufbewahrung (Retention):** neue Options-Option „Aufbewahrung"
  (Monate, Default aus = 0). Aktiviert verschiebt ein Startlauf Einträge älter
  als die gewählte Monatszahl in einen Archiv-Store (Store-Schema v3, Migration
  automatisch); Summen und Lebenszähler bleiben unverändert, der CSV-Export
  umfasst weiterhin die volle Historie.
- **Alt-Installationen: Recorder-Statistik-Einheit „ml" → „mL" (automatisch
  behoben):** Ältere Stände der Integration haben die Volumen-Sensoren mit der
  Einheit „ml" gemeldet — die Recorder-Metadaten der betroffenen Statistiken
  tragen deshalb bis heute „ml" (ohne `unit_class`). Die Sensoren melden
  inzwischen die HA-kanonische Einheit „mL", und Home Assistant verweigert
  deshalb die Fortsetzung der Langzeitstatistik komplett:
  *„The unit of … (mL) cannot be converted to the unit of previously compiled
  statistics (ml). Generation of long term statistics will be suppressed"*.
  Der HA-Kern heilt das nicht von allein (er migriert nur bei einer Änderung
  der `entity_id`), deshalb zieht die Integration die Metadaten **selbst beim
  Setup des Config-Entries** nach — betroffen sind je Person nur die beiden
  Volumen-Sensoren `…_drinks_today` und `…_lifetime_total`.
  - **Verlustfrei:** „ml" und „mL" sind dieselbe physikalische Größe — die
    historischen Werte bleiben gültig, es wird nichts gelöscht und nichts
    umgerechnet.
  - **Idempotent:** Ein zweiter Lauf findet die kanonische Einheit vor und tut
    nichts mehr.
  - **Recorder nicht eingerichtet (deaktiviert):** Die Migration wird dann
    übersprungen und beim nächsten Setup (HA-Neustart oder Reload des
    Config-Entries) nachgeholt — ebenfalls idempotent und verlustfrei.
  - **Log:** Die Meldung wird mit Level **INFO** geloggt
    („Recorder-Statistik-Metadaten migriert (ml → mL)"). Home Assistant loggt
    standardmäßig auf `WARNING` — die Zeile erscheint also nur, wenn das
    Log-Level für `custom_components.health_o_mat` auf `info` steht, z. B. per
    `configuration.yaml`:
    ```yaml
    logger:
      logs:
        custom_components.health_o_mat: info
    ```
  - **Bewusst kein Lösch-Service:** Die Integration bietet **keinen** Service
    an, um betroffene Statistiken zu löschen oder aufzuräumen — die
    Metadaten-Migration ist verlustfrei, und Home Assistant bietet
    „Statistiken löschen" bereits in der UI an.

## Services

```yaml
action: health_o_mat.add_drink
data: { person: "Caro", amount_ml: 250, drink_type: "Kaffee" }

action: health_o_mat.add_blood_pressure
data: { person: "Caro", systolic: 124, diastolic: 82, pulse: 64 }

action: health_o_mat.set_wellbeing
data: { person: "Caro", status: "good" }   # very_bad | bad | okay | good | great

action: health_o_mat.remove_last_entry
data: { person: "Caro", kind: "drinks" }   # drinks (Default) | blood_pressure

action: health_o_mat.export_csv
data: { person: "Caro", dataset: "all" }   # drinks | blood_pressure | all

action: health_o_mat.import_csv
data: { person: "Caro", filename: "health_o_mat_drinks_Caro_20261014-1200.csv" }
# optional: dataset: drinks | blood_pressure | all (default: all = auto-detect)

action: health_o_mat.backup
```

`set_wellbeing` (Wohlbefinden melden) ist im Abschnitt
[Wohlbefinden melden (Service)](#wohlbefinden-melden-service) ausführlich
beschrieben — die Karten-Buttons und der Service nutzen denselben
Store-/Refresh-Pfad wie das Panel.

## Import & Backup

### CSV import

Re-imports a previously exported CSV (or any file in the same format) into one
person's history:

1. Copy the CSV into `/config/health_o_mat_import/` (create the folder if it
   does not exist yet).
2. Call the service:

```yaml
action: health_o_mat.import_csv
data: { person: "Caro", filename: "health_o_mat_drinks_Caro_20261014-1200.csv" }
```

The import is deliberately tolerant: semicolon-separated, UTF-8 with or without
BOM, `#` comment lines, and a missing or deviating header are all accepted.
Existing entries are recognised as duplicates and skipped (drinks by timestamp +
amount, blood pressure by timestamp + systolic + diastolic); unreadable rows are
rejected. A notification reports the outcome as `imported / skipped / rejected`.

### Backup (JSON full export)

```yaml
action: health_o_mat.backup
```

Writes a versioned JSON backup of **all persons and datasets** — every time range
— to `/config/health_o_mat_export/`, using a timestamped filename
(`health_o_mat_backup_<YYYYMMDD-HHMMSS>.json`). It is the basis for a future
restore.

### Data protection

Both services only ever touch private directories:

- `/config/health_o_mat_import/` — import source
- `/config/health_o_mat_export/` — CSV exports and JSON backups

Files are **never** written to `/config/www/`, which would be publicly reachable
through the Home Assistant web server. Keep these folders out of any public
share.

> ℹ️ **Restore is not available yet.** The JSON backup cannot be re-imported
> automatically; a restore feature is still open.

## Dashboard-Beispiele

- [`examples/dashboard.yaml`](examples/dashboard.yaml) — **nur Standard-Karten**
  von Home Assistant (3 Ansichten: Trinken, Blutdruck, Wohlbefinden)
- [`examples/dashboard-mini.yaml`](examples/dashboard-mini.yaml) — Kompaktblock
  (Standard-Karten) zum Einbauen in ein bestehendes Dashboard
- [`examples/dashboard-mushroom.yaml`](examples/dashboard-mushroom.yaml) —
  **Mushroom-Variante** (benötigt HACS-Plugin [Mushroom](https://github.com/piitaya/lovelace-mushroom))
- [`examples/dashboard-card.yaml`](examples/dashboard-card.yaml) — zeigt die
  **mitgelieferte Karte** (`custom:health-o-mat-card`) in drei Konfigurationen
  (kompakt, nur Anzeige, mit Eingaben); nutzt die Karten-Konfiguration aus dem
  Abschnitt [Mitgelieferte Karte](#mitgelieferte-karte-custom-card)

Import: Einstellungen → Dashboards → **Dashboard hinzufügen** →
„Neues Dashboard aus YAML" (Personennamen in den Entity-IDs anpassen).
Alle Varianten zeigen den Gesundheitszustand kontinuierlich: als Gauge/
Bar (`daily_goal_progress`, `wellbeing`-Select im Verlaufsgraph), als
mushroom-Select mit Emoji oder als konfigurierbare Karte.

Alle Beispiel-Dashboards werden **kontinuierlich getestet**: ein
Unit-Test (`tests/test_dashboards.py`) prüft YAML-Struktur und
Entity-Referenzen, und im geteilten HA-Testsystem (`/home/hermes/ha-test`)
verifiziert `bin/check-dashboards examples/*.yaml`, dass jede referenzierte
Entity in der laufenden Instanz tatsächlich existiert.

## Mitgelieferte Karte (Custom Card)

Die Integration liefert eine eigene Lovelace-Karte mit — eine kompakte
Dashboard-Kachel, ohne zusätzliche HACS-Frontend-Abhängigkeit:

- 💧 **Hydration-Ring** — heutige Menge vs. Tagesziel (Prozent + mL), dazu
  Buchungen, der gestrige Wert, ein **Pace-Badge** (auf Kurs / voraus / hinten /
  Ziel erreicht), die **Serie** (`goal_streak` Tage) und optional **Koffein**
  (`caffeine_today` in mg)
- 🩺 **Blutdruck** — letzte Messung (sys/dia/Puls) mit **WHO-Kategorie** und
  Warnhinweis, wenn sie über den konfigurierten Schwellen liegt
- 🙂 **Wohlbefinden** — letzte Meldung mit Emoji und Zeitpunkt, dazu der
  **Wohlbefinden-Score** als Badge (z. B. „4 / 5") und eine **kleine Sparkline**
  der letzten 14 Meldungen. Die Karte bleibt damit eine einbettbare
  Kompaktanzeige — **kein** Panel-Ersatz
- ↩️ **Quick-Drink-Buttons + Undo** — feste Menge buchen oder die letzte
  Buchung zurücknehmen

Über den **Karten-Editor** lassen sich die Person (statt die Config-Entry-ID von
Hand einzutragen) und alle Anzeige-/Eingabe-Blöcke einstellen. Bereiche, die per
Integrations-Feature-Toggle abgeschaltet sind (siehe unten), bleiben auch in der
Karte ausgeblendet.

### Karten-Konfiguration

Alle Schlüssel sind **optional**. Die Anzeige-Blöcke bleiben per Default
unverändert; die **Eingabe-Blöcke** (manuelle Mengen, Blutdruck-Eingabe,
Wohlbefinden-Eingabe) sind standardmäßig **aktiv** — bestehende Karten erhalten
sie beim Update. Das ist eine bewusste neue Funktion (seit **v0.10.0**).
Unbekannte Werte fallen auf den Default zurück (kein Render-Fehler).

| Schlüssel | Typ | Default | Bedeutung |
|---|---|---|---|
| `entry_id` | string | – | Person fest binden (Config-Entry-ID). Ohne Angabe wählt die Karte die erste Person bzw. zeigt eine Auswahl. |
| `person` | string | – | Optionaler Service-Anker für Schreibaufrufe (Name aus dem Config-Entry). |
| `show_person` | bool | `true` | Personen-Dropdown im Kopf. `false` ohne `entry_id` → erste Person, keine Auswahl. |
| `show_hydration` | bool | `true` | Hydration-Ring, Tageswerte, Pace, Serie, Koffein. |
| `show_blood_pressure` | bool | `true` | Letzte Blutdruckmessung inkl. WHO-Kategorie und Warnung. |
| `show_wellbeing` | bool | `true` | Letztes Wohlbefinden, Score und Sparkline. |
| `show_drinks` | bool | `true` | Quick-Drink-Buttons. |
| `show_manual_amounts` | bool | `true` | Preset-Buttons für ml-Mengen (und ggf. freies Feld). |
| `show_blood_pressure_input` | bool | `true` (folgt `show_blood_pressure`) | Eingabe Systolisch/Diastolisch/Puls inkl. Notiz. |
| `show_wellbeing_input` | bool | `true` | Die fünf Wohlbefinden-Buttons. |
| `show_undo` | bool | `true` | Undo der letzten Getränkebuchung. |
| `drinks` | list[str] | alle | Keys der Quick-Drinks aus der Integration (`panel_data.quick_drinks`); unbekannte Keys werden ignoriert, leer/fehlend = alle. |
| `manual_amounts` | list[int] | `[200, 500]` | ml-Presets (1…10000); leer/fehlend = Default. |
| `allow_custom_amount` | bool | `true` | Zusätzliches freies Zahlenfeld mit Buchen-Button. |
| `quick_drinks` | list[object] | – | Legacy-Override (`[{label, ml, emoji}]`); gewinnt gegenüber `drinks` und der Integrationsliste. |

**Semantik:** `show_*=false` blendet den Block samt zugehöriger Eingaben aus.
Ein **explizit** gesetztes `show_blood_pressure_input: true` hat Vorrang vor
`show_blood_pressure: false` (die Eingabe bleibt sichtbar). Sind alle Blöcke aus,
zeigt die Karte einen lesbaren Hinweis statt einer leeren Fläche.

**Beispiele**

Minimal (alle Defaults):

```yaml
type: custom:health-o-mat-card
entry_id: <config-entry-id>
```

Nur Anzeige, ohne Eingaben und Aktionen:

```yaml
type: custom:health-o-mat-card
entry_id: <config-entry-id>
show_person: false
show_drinks: false
show_manual_amounts: false
show_blood_pressure_input: false
show_wellbeing_input: false
show_undo: false
```

Mit Eingaben, Getränkeauswahl und eigenen Mengen:

```yaml
type: custom:health-o-mat-card
entry_id: <config-entry-id>
person: Caro
drinks: ["slot_0", "kaffee"]
manual_amounts: [200, 330, 500]
allow_custom_amount: true
show_blood_pressure_input: true
show_wellbeing_input: true
```

### Wohlbefinden melden (Service)

Die Wohlbefinden-Buttons der Karte schreiben über den öffentlichen Service:

```yaml
action: health_o_mat.set_wellbeing
data:
  person: "Caro"   # optional — ohne Angabe die einzige konfigurierte Person
  status: "good"   # Pflicht: very_bad | bad | okay | good | great
```

Ein unbekannter `status` wird mit `ServiceValidationError` abgelehnt. Die
bestehenden `button.*_report_*`-Entities bleiben unverändert und nutzen
denselben Store-/Refresh-Pfad.

Die Karte wird unter `/health_o_mat/health-o-mat-card.js` ausgeliefert und beim
Setup automatisch als Lovelace-Ressource registriert (idempotent) — die
Ressource muss **nicht** von Hand hinzugefügt werden. Eine zusätzliche
Frontend-Abhängigkeit (z. B. Mushroom) ist **nicht** nötig.

Einbindung in eine Dashboard-Ansicht per YAML:

```yaml
type: custom:health-o-mat-card
entry_id: <config-entry-id>   # optional — ohne Angabe erscheint eine Personenauswahl
```

Ohne `entry_id` (bzw. bei mehreren Personen) zeigt die Karte automatisch eine
Personenauswahl.

Die Karte liefert die Integration immer mit — unabhängig vom unten beschriebenen
Panel.

## Sidebar-Panel (optional)

Optional liefert die Integration ein **Sidebar-Panel** `health-o-mat-panel` —
eine app-artige Vollbild-Ansicht, die sich als eigener Menüpunkt in die
HA-Seitenleiste einklinkt:

- 👥 **Mehr-Personen-Übersicht** — eine Kachel je Person (Hydration-Ring, letzte
  Blutdruckwerte, Wohlbefinden), inklusive Status
- 📑 **Person-Detail mit Tabs** — Trinken · Blutdruck · Wohlbefinden; Buchen,
  Messen und Melden funktionieren direkt aus dem Panel. Bereiche, die per
  Feature-Toggle abgeschaltet sind, werden ausgeblendet
- 📈 **Wohlbefinden-Score-Chart** — im Tab „Wohlbefinden" zeigt das Panel den
  **vollständigen Verlaufs-Chart** des Scores: Zeit auf der X-Achse, Score 1–5
  auf der Y-Achse (Extremwerte 1 und 5 hervorgehoben), Zeitachse und der
  aktuelle Wert als hervorgehobener Marker. Chart **ohne externe Bibliothek**
  (Vanilla-SVG), Farben ausschließlich über HA-CSS-Variablen → light/dark-fähig
- 🔗 **Deep-Link pro Person** — die Person-Ansicht ist direkt verlinkbar über
  `?person=<slug>`, z. B. `/health-o-mat?person=caro`. Als Kennung dient der
  **stabile** Personen-Schlüssel (nie der Anzeigename), sodass ein Link eine
  Umbenennung übersteht
- 🔄 **Live-Aktualisierung** — Schreibvorgänge und externe Änderungen landen ohne
  Neuladen im Panel (WebSocket-Refresh statt Polling)
- 🙋 **Per-User-Auswahl** — das Panel merkt sich je HA-Nutzer die zuletzt gewählte
  Person (nur ein UI-Zustand, **keine** Gesundheitsdaten)

**Das Panel ist opt-in (Default aus).** Ein-/ausgeschaltet wird es pro Person im
Options-Dialog der Integration über den Schalter **„Sidebar-Panel anzeigen"**
(`enable_sidebar_panel`): Einstellungen → Geräte & Dienste → **HA Health-O-Mat**
→ *Konfigurieren* → Optionen → Schalter setzen. Sobald **eine** Person das Panel
aktiviert, teilen sich alle Personen **ein** gemeinsames Sidebar-Panel
(„Health-O-Mat"); ohne gesetzte Option bleibt die Seitenleiste unverändert.

### Admin-/Settings-Ansicht (L3, nur für HA-Administratoren)

Ist der angemeldete HA-Nutzer **Administrator**, zeigt das Panel zusätzlich eine
**⚙️ Settings-Ansicht**. Dort lassen sich die Einstellungen einer Person an
**einem** Ort verwalten (dieselben Schlüssel wie der Options-Dialog — nur als
eine scrollbare Maske statt drei erzwungener Options-Schritte):

- 🎯 **Tagesziel** (mL) und **Reset-Uhrzeit** (0–23 Uhr)
- 🏷️ **Anzeigename** der Person
- 🥤 **Quick-Drink-Slots** (4, je Label/Icon/mL)
- 📖 **Getränke-Lexikon** — eine Zeile je Wort im Format `wort=Typ,ml`, mit
  Zeilen-Validierung (die Fehlermeldung nennt die betroffene Zeile)
- 🩺 **Blutdruck-Warnschwellen** (sys/dia) — wirken zur Laufzeit sofort auf den
  Blutdruck-Warn-Binary-Sensor
- 🗄️ **Aufbewahrung** (Retention in Monaten)
- 🧩 **Feature-Toggles pro Person** — **Trinken / Blutdruck / Wohlbefinden**
  einzeln an/aus. Ein abgeschalteter Bereich erzeugt **keine** Entities mehr
  (sie werden beim Reload entladen); `unique_id` und Historie bleiben
  **unverändert**, ein Wieder-Einschalten erzeugt dieselbe `entity_id` wieder.
  Fehlt die Auswahl (Alt-Entry), sind alle Bereiche aktiv
- 📌 **Sidebar-Panel-Schalter** (Opt-in)
- 📄 **CSV-Export** direkt aus dem Panel anstoßen
  (`drinks` / `blood_pressure` / `all`, geschrieben nach
  `/config/health_o_mat_export/`)
- 💾 **Backup** direkt aus dem Panel auslösen (ruft den `health_o_mat.backup`-Service)
- ➕ **Person anlegen** — öffnet den Standard-HA-Config-Flow (kein eigener Dialog)
- 🗑️ **Person löschen** — nur Admin, mit **Doppelbestätigung** (die Bestätigung
  muss dem Personen-Schlüssel entsprechen). **Achtung:** Das Löschen entfernt
  nur die Integration samt Entities — der Store wird nicht aufgeräumt, und ein
  **Restore des Backups ist weiterhin nicht implementiert**; vorher ein Backup
  erstellen

**Schreibrechte:** Die **Alltagseingaben bleiben für alle HA-Nutzer offen** —
Buchen, Messen, Melden und Undo funktionieren unabhängig von Admin-Rechten. Nur
die **Settings-Ansicht, der Export, das Backup sowie Anlegen/Löschen von
Personen sind auf HA-Administratoren beschränkt** und serverseitig hart
abgesichert; Nicht-Admins erhalten einen sauberen Fehler statt Zugriff.

### Feature-Toggles & Entities

Die Pro-Person-Toggles (REQ-HOM-009) sind auch über den regulären Options-Dialog
erreichbar (Schalter „Trinken erfassen" / „Blutdruck erfassen" / „Wohlbefinden
erfassen") und wirken identisch. Das Abschalten **löscht** keine Daten: Es werden
lediglich die Entities des Bereichs nicht mehr geladen. Deaktivierte Entities
erscheinen in Home Assistant als `unavailable` (bzw. sind nach einem Neustart
nicht mehr vorhanden); ihre Registry-Einträge und `unique_id`s bleiben bestehen.

Die oben beschriebene Lovelace-Karte (`custom:health-o-mat-card`) bleibt davon
unberührt und funktioniert unabhängig vom Panel.

## E2E-Tests (Playwright)

Der Deep-Link des Panels (`?person=<slug>`) ist als **echter Browser-Test**
abgesichert: `tests_e2e/` fährt eine **reale Home-Assistant-Instanz** mit
**Chromium** (Playwright) an. Das Panel ist ein bundler-freies Vanilla-JS-Web-
Component ohne Python-Testfläche — ein realer Browser ist die einzige
Möglichkeit, sein Verhalten (URL-Zustand, Historie, Tabs) wirklich zu prüfen.

Abgedeckt (`tests_e2e/test_panel_deeplink_e2e.py`, REQ-HOM-012):

- Panel mountet unter `/health-o-mat` (genau ein `health-o-mat-panel`)
- `?person=<slug>` öffnet **direkt** die Person-Detailansicht samt Tabs
- Klick auf eine Personen-Kachel setzt `?person=<slug>` per
  `history.pushState`
- **Browser-Zurück** stellt die Übersicht wieder her und entfernt den
  Parameter (`popstate`)
- Unbekannter/ungültiger Parameter → sichere Übersicht, kein Fehlerzustand
- Ein per Feature-Toggle abgeschalteter Bereich blendet seinen Tab aus

**Nicht Teil der Unit-Suite:** `pytest` im Repo-Root sammelt weiterhin nur
`tests/` ein. Die Browser-Suite hat eine eigene Konfiguration
(`tests_e2e/pytest.ini`) und läuft nur bei explizitem Aufruf.

### Lokal ausführen

Vollständiger Stack (HA-Container + Playwright-Runner-Image, wie in CI):

```bash
docker compose -f docker-compose.e2e.yml up --build \
    --abort-on-container-exit --exit-code-from e2e
docker compose -f docker-compose.e2e.yml down -v
```

Leichtgewichtig (HA im Container, Playwright lokal — spart das Browser-Image;
der HA-Port ist per `E2E_HA_PORT` einstellbar, Default **8124**, damit eine
parallel laufende HA-Instanz auf 8123 nicht kollidiert):

```bash
pip install -r requirements_e2e.txt && playwright install chromium
docker compose -f docker-compose.e2e.yml up -d homeassistant
HASS_BASE_URL=http://localhost:8124 pytest tests_e2e/ -v
docker compose -f docker-compose.e2e.yml down
```

Gegen eine bereits laufende Instanz (auch das geteilte Testsystem
`/home/hermes/ha-test`) — Zugangsdaten per Env, sonst werden die
Standard-E2E-Zugangsdaten verwendet:

```bash
HASS_BASE_URL=http://localhost:8123 \
HASS_USERNAME=healthbot HASS_PASSWORD=<Passwort> \
pytest tests_e2e/ -v
```

`scripts/e2e_bootstrap.py` bereitet die Instanz **idempotent** vor: Onboarding
(alle vier Schritte) bzw. Login auf einer bereits eingerichteten Instanz,
Zugriffstoken und zwei eigene Test-Personen (`E2E-Deep` mit allen Bereichen,
`E2E-Tab` mit abgeschaltetem Blutdruck-Bereich) samt Optionen — angelegt über
den echten Config- bzw. Options-Flow, inklusive `enable_sidebar_panel` (ohne
die Option gäbe es das Panel gar nicht). Fremde Personen/Config-Entries werden
nur gelesen, nie verändert; fehlen die Test-Personen, werden sie angelegt,
sonst wiederverwendet. Das CLI gibt den Zustand als JSON aus
(`python scripts/e2e_bootstrap.py --base-url http://localhost:8124`).

Hinweis: `docker/ha_config_e2e/` ist ein Host-Bind-Mount — `down -v` setzt den
HA-Zustand darin **nicht** zurück (`.storage/`, Recorder-DB, Onboarding-Flag).
Für einen bewusst frischen Lauf vorher löschen (siehe
`.github/workflows/e2e.yaml`, dort passiert genau das). Das Artefakt-Verzeichnis
`test-results/` wird von Playwright zu Beginn **jedes** pytest-Laufs geleert
(Screenshots/Traces also nur pro Lauf frisch); es ist nicht versioniert.

In CI läuft die Suite **nicht** bei jedem Push: `.github/workflows/e2e.yaml`
startet bei `workflow_dispatch`, wöchentlich per `schedule` und bei Pull
Requests, die `custom_components/health_o_mat/**`, `tests_e2e/**`,
`docker-compose.e2e.yml`, `Dockerfile.e2e`, `docker/ha_config_e2e/**` oder
`scripts/e2e_bootstrap.py` berühren.

## Lizenz

MIT — siehe [LICENSE](LICENSE).

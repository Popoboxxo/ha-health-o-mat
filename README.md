# HA Health-O-Mat

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![Validate](https://github.com/Popoboxxo/ha-health-o-mat/actions/workflows/validate.yml/badge.svg)

**Trinken & Blutdruck im Blick** — das Gesundheits-Tagebuch für Home Assistant.
Lokal, dauerhaft gespeichert (überlebt jeden Recorder-Purge), alles als native
Entities verfügbar und jederzeit als Excel-taugliche CSV exportierbar.

> ⚠️ Keine medizinische Beratung — Klassifikationen/Warnungen dienen nur der Orientierung.

## Features

- 💧 **Getränke-Tracking**: „Wie viel habe ich heute getrunken?" — sauberer ml-Sensor,
  Prozent-Gauge, Breakdown nach Getränketyp
- 🔘 **Quick-Drink-Buttons** (Glas Wasser 200 · Flasche 500 · Kaffee 250 · Saft 200)
  + Custom-Menge + **Freitextfeld** mit Parser: `Kaffee 300ml`, `0,5 l wasser`,
  `cola`, `Ingwertee 400` — alles funktioniert
- 🩺 **Blutdruck**: Eingabefelder (sys/dia/puls) + Speichern-Button, Verlaufs-Sensoren,
  7-Tage-Mittelwert, konfigurierbare Warnschwelle (Default 140/90)
- ↩️ **Undo-Button** für die letzte Buchung
- 📄 **CSV-Export** per Service → `/config/health_o_mat_export/`
  (Semikolon + UTF-8-BOM = Excel-Doppelklick-tauglich)
- 👥 **Multi-Person**: ein Config-Entry = eine Person = ein Device — beliebig viele
- 🌙 **Tagesgrenze**: fix 0 Uhr; neustartfest, weil „heute" on-read aus der Historie
  berechnet wird (kein Reset-Job, DST-fest) — umstellbare Tagesgrenze ist geplant
  ([REQ-HOM-005](docs/REQUIREMENTS.md))

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
| sensor | `drinks_today` | Heute getrunken / Drinks today | **ml heute** (+ count, %, breakdown, gestern) |
| sensor | `daily_goal_progress` | Tagesziel-Fortschritt / Daily goal progress | Gauge-fähig |
| sensor | `drinks_history` | Getränke-Historie / Drinks history | Rohdaten als JSON-Attribut |
| sensor | `lifetime_total` | Gesamtmenge / Lifetime total | kumuliert |
| sensor | `blood_pressure_systolic` / `blood_pressure_diastolic` / `pulse` | Blutdruck systolisch / diastolisch, Puls | letzte Messung (measurement → Graph) |
| sensor | `blood_pressure_history` | Blutdruck-Historie / Blood pressure history | letzte 30 Messungen als JSON |
| sensor | `wellbeing_last_reported` | Wohlbefinden zuletzt gemeldet / Wellbeing last reported | Zeitstempel |
| binary_sensor | `daily_goal_reached` / `blood_pressure_warning` | Tagesziel erreicht, Blutdruck-Warnung | Status |
| button | Quick-Drinks (Label aus der Konfiguration), `book_custom_amount`, `undo_last_drink`, `save_measurement` | Buchen/Löschen/Speichern | Alltagseingabe |
| button | `report_very_bad` … `report_great` | Melden: … / Report: … | Wohlbefinden |
| select | `wellbeing` | Wohlbefinden / Wellbeing | Optionen werden ebenfalls übersetzt |
| text | `log_drink_free_text` | Getränk buchen (Freitext) | „Kaffee 300ml" → Enter = buchen |
| number | `daily_goal`, `custom_drink_amount`, `systolic/diastolic_warning_threshold`, `new_reading_*` | Tagesziel, Eigenmenge, Warnschwellen, BP-Eingabe | Runtime-Einstellungen |

### Entities im Detail

**Sensoren**

- `sensor.…_drinks_today` — getrunkene Menge des heutigen Tagesfensters in ml.
  Attribute: `drinks_count` (Buchungen heute), `percent_of_goal` (Fortschritt),
  `breakdown_by_type` (JSON: ml je Getränketyp), `last_drink_at`,
  `yesterday_ml` (Vortag, gleiche Tagesgrenze).
- `sensor.…_daily_goal_progress` — Prozent des Tagesziels (0–100), für
  Gauge-/Bar-Karten; `state_class: measurement` → Verlaufsgraph.
- `sensor.…_drinks_history` — Zustand = Anzahl Buchungen heute; Attribut
  `entries_json` = komplette Rohhistorie als JSON (Zeitstempel, ml, Typ,
  Quelle). Für Automatisierungen und Backup-Zwecke.
- `sensor.…_lifetime_total` — kumulierte Gesamtmenge in ml seit Start
  (`state_class: total_increasing` → Langzeitstatistik ohne Zähler-Rücksetzungen).
  Startwert beim Integration-Setup eintragbar (z. B. Migration vom alten
  Wasser-Zähler).
- `sensor.…_blood_pressure_systolic` / `_diastolic` / `_pulse` — die letzte
  gemessene Messung (mmHg / BPM, `state_class: measurement` → HA-Historie
  zeichnet automatisch auf). Attribute: `measured_at`, `avg_7d` (Mittelwert
  über ein echtes rollierendes 7-Tage-Fenster), `readings_total`.
- `sensor.…_blood_pressure_history` — Zustand = Gesamtzahl der Messungen;
  Attribut `history_json` = die letzten 30 Messungen als JSON.
- `sensor.…_wellbeing_last_reported` — Zeitstempel der letzten
  Wohlbefinden-Meldung (`device_class: timestamp`).

**Binary-Sensoren**

- `binary_sensor.…_daily_goal_reached` — `on`, sobald das Tagesziel erreicht
  ist (ideal für Benachrichtigungen: „triggern auf on").
- `binary_sensor.…_blood_pressure_warning` — `on`, wenn die letzte Messung
  über den konfigurierbaren Warnschwellen liegt (Defaults 140/90 mmHg,
  änderbar über die Number-Entities `…_systolic_warning_threshold` /
  `…_diastolic_warning_threshold`).

**Buttons**

- **Quick-Drinks** — je konfiguriertem Quick-Drink ein Button (Label, ml und
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
  per Regex (ml/l, auch Dezimal mit Komma/Punkt) und ordnet die restlichen
  Wörter über ein eingebautes Lexikon (wasser/water, kaffee/coffee, tee/tea,
  bier/beer, wein/wine, milch/milk, cola, limo, saft/juice, sekt …) einem
  Getränketyp zu; unbekannte Typen werden wörtlich übernommen.
  **Gespeichert wird nur das strukturierte Ergebnis** (Zeitstempel, ml, Typ,
  Quelle `freetext`) — der Rohtext landet **nicht** in der Historie; er bleibt
  kurzlebig in den Entity-Attributen (`last_input`, `drink_type`,
  `amount_ml`) und wird beim nächsten Setzen überschrieben. Nicht erkennbare
  Eingaben erzeugen einen Entity-Fehler mit Lösungsbeispielen, statt
  stillschweigend etwas zu buchen.

**Numbers (Laufzeit-Einstellungen)**

- `number.…_daily_goal` — Tagesziel in ml (sofort wirksam, persistiert via
  Options-Flow).
- `number.…_custom_drink_amount` — Menge für den „Eigenen Betrag buchen"-Button.
- `number.…_systolic_warning_threshold` / `_diastolic_warning_threshold` —
  Warnschwellen für den Blutdruck-Warn-Binary-Sensor.
- `number.…_new_reading_systolic` / `_diastolic` / `_pulse` — Eingabefelder
  für die nächste Blutdruckmessung (mit `save_measurement`-Button übernehmen).

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

## Services

```yaml
action: health_o_mat.add_drink
data: { person: "Caro", amount_ml: 250, drink_type: "Kaffee" }

action: health_o_mat.add_blood_pressure
data: { person: "Caro", systolic: 124, diastolic: 82, pulse: 64 }

action: health_o_mat.remove_last_entry
data: { person: "Caro", kind: "drinks" }

action: health_o_mat.export_csv
data: { person: "Caro", dataset: "all" }   # drinks | blood_pressure | all
```

## Dashboard-Beispiele

- [`examples/dashboard.yaml`](examples/dashboard.yaml) — **nur Standard-Karten**
  von Home Assistant (3 Ansichten: Trinken, Blutdruck, Wohlbefinden)
- [`examples/dashboard-mini.yaml`](examples/dashboard-mini.yaml) — Kompaktblock
  (Standard-Karten) zum Einbauen in ein bestehendes Dashboard
- [`examples/dashboard-mushroom.yaml`](examples/dashboard-mushroom.yaml) —
  **Mushroom-Variante** (benötigt HACS-Plugin [Mushroom](https://github.com/piitaya/lovelace-mushroom))

Import: Einstellungen → Dashboards → **Dashboard hinzufügen** →
„Neues Dashboard aus YAML" (Personennamen in den Entity-IDs anpassen).
Beide Varianten zeigen den Gesundheitszustand kontinuierlich: als Gauge/
Bar (`daily_goal_progress`, `wellbeing`-Select im Verlaufsgraph) bzw. als
mushroom-Select mit Emoji.

Alle Beispiel-Dashboards werden **kontinuierlich getestet**: ein
Unit-Test (`tests/test_dashboards.py`) prüft YAML-Struktur und
Entity-Referenzen, und im geteilten HA-Testsystem (`/home/hermes/ha-test`)
verifiziert `bin/check-dashboards examples/*.yaml`, dass jede referenzierte
Entity in der laufenden Instanz tatsächlich existiert.

## Lizenz

MIT — siehe [LICENSE](LICENSE).

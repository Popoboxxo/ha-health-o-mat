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
- 🌙 **Tagesgrenze**: Default 0 Uhr, zur Laufzeit umstellbar; neustartfest, weil „heute"
  on-read aus der Historie berechnet wird (kein Reset-Job, DST-fest)

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

### Migration (Entity-ID-Neuregistrierung, Update von v0.2.0 oder älter)

Die unique_ids wurden auf das neue Schema umgestellt: Betroffene Entities
(Sensoren, Wohlbefinden-Select, Melden-Buttons) registrieren sich beim ersten
Start nach dem Update **neu mit englischen IDs** (alte Einträge erscheinen als
verwaiste Entities im Entity-Registry und können dort gelöscht werden).
Getränke-/Messdaten bleiben erhalten — sie hängen am Config-Entry, nicht an
der Entity-ID. Automationen/Dashboards mit alten (teils deutschen) Entity-IDs
müssen einmalig umgestellt werden; Vorlage siehe `examples/`.

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

- [`examples/dashboard.yaml`](examples/dashboard.yaml) — komplettes Dashboard
  (3 Ansichten: Trinken, Blutdruck, Wohlbefinden)
- [`examples/dashboard-mini.yaml`](examples/dashboard-mini.yaml) — Kompaktblock
  zum Einbauen in ein bestehendes Dashboard

Import: Einstellungen → Dashboards → **Dashboard hinzufügen** →
„Neues Dashboard aus YAML" (Personennamen in den Entity-IDs anpassen).

## Lizenz

MIT — siehe [LICENSE](LICENSE).

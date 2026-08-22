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

## Entities (je Person)

| Typ | Entity | Zweck |
|---|---|---|
| sensor | `Heute getrunken` | **ml heute** (+ Attribute: count, %, breakdown, gestern) |
| sensor | `Tagesziel Prozent` | Gauge-fähig |
| sensor | `Getränke Historie` | Rohdaten als JSON-Attribut |
| sensor | `Gesamt (Lebenszähler)` | kumuliert |
| sensor | `Blutdruck Systolisch/Diastolisch/Puls` | letzte Messung (measurement → Graph) |
| sensor | `Blutdruck Verlauf` | letzte 30 Messungen als JSON |
| binary_sensor | `Tagesziel erreicht` / `Blutdruck Warnung` | Status |
| button | Quick-Drinks, Eigenen Betrag buchen, Letzte Buchung löschen, Messung speichern | Alltagseingabe |
| text | `Freitext Getränk` | „Kaffee 300ml" → Enter = buchen |
| number | Tagesziel, Eigenmenge, Warnschwellen, BP-Eingabefelder | Runtime-Einstellungen |

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

## Dashboard-Beispiel

Siehe [`examples/dashboard.yaml`](examples/dashboard.yaml).

## Lizenz

MIT — siehe [LICENSE](LICENSE).

# HA Health-O-Mat

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![Validate](https://github.com/Popoboxxo/ha-health-o-mat/actions/workflows/validate.yml/badge.svg)

**Trinken & Blutdruck im Blick** — das Gesundheits-Tagebuch für Home Assistant.
Lokal, dauerhaft gespeichert (überlebt jeden Recorder-Purge), alles als native
Entities verfügbar und jederzeit als Excel-taugliche CSV exportierbar.

> ⚠️ Keine medizinische Beratung — Klassifikationen/Warnungen dienen nur der Orientierung.

> 📝 Änderungen: [CHANGELOG.md](CHANGELOG.md) · Releases:
> [GitHub Releases](https://github.com/Popoboxxo/ha-health-o-mat/releases)

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
  heute und der **Wohlbefinden-Score (1–10)** — je eine Entity für den
  Entscheidungswert, Details als Attribute
- ↩️ **Verlauf & Korrigieren**: je Datentyp (Getränke, Blutdruck, Wohlbefinden)
  ein Verlauf mit **Löschen (Void)**, **Wiederherstellen (Restore)** und
  **Undo** — kein Hard-Delete in der UI, Korrekturen werden auditierbar
  protokolliert
- 🕒 **Rückdatieren**: Buchungen/Messungen/Meldungen mit Zeitpunkt nachtragen
  (unbegrenzt zurück, nie in die Zukunft); „Jetzt"/„Gestern" als Schnellwahl
- 🌍 **Deutsch/Englisch**: Panel, Karte, Editor und Admin folgen der
  HA-Sprache (`hass.language`), mit deutschem Fallback
- 🔔 **Erinnerungen & Wochenbericht**: Trink-/BD-/Wohlbefinden-Erinnerungen und
  ein Wochenbericht als Notification (optional per Scheduler), plus importierbare
  Blueprints
- 🧭 **Options-Wizard**: Grundlagen, Getränke, Wohlbefinden, Benachrichtigungen
  und Defaults in optionalen Schritten — eine neue Person ist sofort einsatzbereit
- 📄 **CSV-Export** per Service → `/config/health_o_mat_export/`
  (Semikolon + UTF-8-BOM = Excel-Doppelklick-tauglich; exportiert nur **aktive**
  Einträge, das Archiv bleibt enthalten)
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

## Schnellstart: Person anlegen, Defaults nutzen

Eine neu angelegte Person ist **sofort einsatzbereit**, ohne dass der
Options-Dialog geöffnet werden muss: Die Quick-Drinks (Glas Wasser, Flasche
Wasser, Tasse Kaffee, Glas Saft), das eingebaute Getränke-Lexikon und
ausgeschaltete Erinnerungen greifen automatisch. Eigene Wellbeing-Bilder sind
leer (es erscheinen die Emojis). Anpassen lässt sich alles später unter
Einstellungen → Geräte & Dienste → **HA Health-O-Mat** → *Konfigurieren*.

### Options-Wizard

Der Options-Dialog ist ein **Menü mit optionalen Abschnitten**. Änderungen
werden nur vorgemerkt und erst in der Zusammenfassung gespeichert:

| Abschnitt | Inhalt |
|---|---|
| **Grundlagen** | Tagesziel, Lebenszähler-Startwert, Anzeigename, Tages-Reset, Aufbewahrung, Sidebar-Panel, Bereichs-Toggles |
| **Getränke** | Quick-Drinks **und** Getränke-Lexikon in einem Formular (Lexikon mit Zeilen-Validierung) |
| **Wohlbefinden** | Eigene Bilder je Stufe (optional, sonst Emojis) |
| **Benachrichtigungen** | Erinnerungen und Wochenbericht (Standard: aus) |
| **Defaults übernehmen** | Setzt Standard-Quick-Drinks, eingebautes Lexikon, leere Bilder und ausgeschaltete Erinnerungen |
| **Zusammenfassung** | Zeigt die geänderten Schlüssel/Werte; **Speichern** übernimmt sie |

- Jeder **optionale** Abschnitt (Grundlagen, Getränke, Wohlbefinden,
  Benachrichtigungen) hat **„Diesen Schritt überspringen"** — er kehrt dann ohne
  Änderung ins Menü zurück. Die Zusammenfassung ist der Speicherpunkt.
- **Direkte Navigation:** Jeder Menüpunkt ist jederzeit erreichbar; die
  Zusammenfassung ist der einzige Speicherpunkt.
- **Nichts geht verloren:** Optionen, die in diesem Lauf nicht geändert werden
  (u. a. `wellbeing_confirm`, `audit_limit` sowie die genesteten `reminders`- und
  `weekly_report`-Strukturen), bleiben beim Speichern unverändert erhalten.
  Ein Abbruch des Dialogs ändert nichts.
- **Defaults sofort nutzbar:** Eine neu angelegte Person arbeitet ohne
  Options-Dialog mit den Standard-Quick-Drinks, dem eingebauten Lexikon, leeren
  Wohlbefinden-Bildern und ausgeschalteten Erinnerungen. Wer nichts anpassen
  will, überspringt die optionalen Schritte und speichert direkt.

Die benachrichtigungsbezogenen Optionen (Erinnerungen, Wochenbericht) sind im
Abschnitt [Erinnerungen, Wochenbericht & Blueprints](#erinnerungen-wochenbericht--blueprints)
beschrieben.

## Erinnerungen, Wochenbericht & Blueprints

### Erinnerungen (Options-Schritt „Benachrichtigungen")

Erinnerungen sind pro Person **standardmäßig aus** und ändern ohne explizites
Aktivieren nichts am bisherigen Verhalten. Einstellbar sind:

- **Uhrzeit** und **Wochentage** (leer/ungültig = alle Tage)
- **Notify-Service** (jeder `notify.*`-Dienst; `notify.mobile_app_x` und
  `mobile_app_x` werden gleich behandelt)
- **Quiet Hours** (optionales Ruhefenster, auch über Mitternacht)
- **Bedingungen**: Tagesziel noch nicht erreicht, seit X Stunden nichts
  getrunken, seit X Tagen keine Blutdruckmessung, seit X Tagen keine
  Wohlbefinden-Meldung

Die Erinnerungen laufen über einen Scheduler je Config-Entry, werden bei
Options-Änderungen neu aufgesetzt und **pro Tag dedupliziert**. Ausgewertet wird
die aktive Store-Sicht (gelöschte Einträge zählen nicht); es gibt keinen
Reset-Job. Ist kein `notify.*`-Dienst gesetzt oder schlägt die Zustellung fehl,
fällt die Integration auf **`persistent_notification`** zurück; Zustellfehler
sind sichtbar, blockieren aber nie das Setup.

### Wochenbericht

Der Wochenbericht fasst die letzten sieben Tage je Person als
**Markdown-Notification** zusammen — **es wird keine Datei geschrieben**.
Er ist als Service (`health_o_mat.weekly_report`, Abschnitt
[Services](#services)) und optional geplant (Wochentag + Uhrzeit im
Options-Schritt „Benachrichtigungen") verfügbar. Ohne `person` erhält jede
eingerichtete Person einen eigenen Bericht.

### Blueprints

Unter `blueprints/automation/health_o_mat/` liegen drei importierbare
Automationen:

- `evening_reminder.yaml` — Abend-Erinnerung, wenn das Tagesziel noch nicht
  erreicht ist
- `blood_pressure_warning.yaml` — Benachrichtigung bei Blutdruck-Warnung
- `weekly_report.yaml` — ruft den Wochenbericht-Service auf

**Wichtig:** HACS installiert Blueprints **nicht automatisch**. Die YAML-Dateien
müssen manuell importiert werden (Einstellungen → Automationen & Szenen →
Blueprints → Blueprint importieren, z. B. per GitHub-URL oder Datei-Upload).
Jeder Blueprint hat eine frei wählbare Person bzw. Entity-Auswahl und
zweisprachige Beschreibungen.

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
| sensor | `wellbeing_score` | Wohlbefinden-Score / Wellbeing score | numerisches Wohlbefinden 1–10 (rein abgeleitet) |
| sensor | `blood_pressure_category` | Blutdruck-Kategorie / Blood pressure category | WHO-Kategorie der letzten Messung (optimal … hypertensive Krise) |
| sensor | `drinks_trend` | Trink-Trend / Drinks trend | ± % heute vs. Vorwochen-Ø (mL) |
| sensor | `blood_pressure_trend` | Blutdruck-Trend / Blood pressure trend | steigend/fallend/stabil aus 7-Tage-Mitteln |
| sensor | `goal_streak` | Ziel-Serie / Goal streak | Tage in Folge mit erreichtem Tagesziel (+ Bestwert) |
| sensor | `caffeine_today` | Koffein heute / Caffeine today | **geschätzte** mg Koffein heute |
| binary_sensor | `daily_goal_reached` / `blood_pressure_warning` | Tagesziel erreicht, Blutdruck-Warnung | Status |
| button | Quick-Drinks (Label aus der Konfiguration), `book_custom_amount`, `undo_last_drink`, `save_measurement` | Buchen/Void/Speichern | Alltagseingabe |
| button | `report_very_bad` … `report_excellent` | Melden: … / Report: … | Wohlbefinden (zehn Stufen) |
| select | `wellbeing` | Wohlbefinden / Wellbeing | Optionen werden ebenfalls übersetzt |
| text | `log_drink_free_text` | Getränk buchen (Freitext) | „Kaffee 300ml" → Enter = buchen |
| number | `daily_goal`, `custom_drink_amount`, `systolic/diastolic_warning_threshold`, `new_reading_*`, `wellbeing_input` | Tagesziel (mL), Eigenmenge (mL), Warnschwellen, BP-Eingabe, Wohlbefinden-Zahl | Runtime-Einstellungen und Scores |

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
  der Skala 1 … 10**: 1 = „Sehr schlecht" (schlechtester Wert) … 10 =
  „Ausgezeichnet" (bester Wert). Die Skala ist **reihenfolgetreu aus den zehn
  Wohlbefinden-Zuständen abgeleitet** (Position in der Zustandsliste + 1).
  `state_class: measurement` (→ HA-Statistik/Graph nutzbar), **ohne Einheit
  und ohne `device_class`** (der Score ist dimensionslos). Ohne Meldung ist der
  Zustand `unknown` — **nie 0** (0 wäre der schlechteste Wert und würde den
  Verlauf verfälschen). Attribute: `reported_at` (Zeitpunkt der Meldung) und
  `scale_max` (10). Der Wert ist **rein abgeleitet**.

**Wohlbefinden-Score: die Skala 1 … 10**

| Score | Key | Emoji | Zustand |
|---|---|---|---|
| 1 | `very_bad` | 😭 | Sehr schlecht |
| 2 | `awful` | 😖 | Elend |
| 3 | `bad` | 🙁 | Schlecht |
| 4 | `poor` | 😔 | Mäßig |
| 5 | `okay` | 😐 | Okay |
| 6 | `mixed` | 😕 | Durchwachsen |
| 7 | `good` | 🙂 | Gut |
| 8 | `very_good` | 😊 | Sehr gut |
| 9 | `great` | 😄 | Großartig |
| 10 | `excellent` | 🤩 | Ausgezeichnet |

Die bestehenden Keys (`very_bad`, `bad`, `okay`, `good`, `great`) bleiben
erhalten und liegen auf den ungeraden Stufen 1/3/5/7/9 — alte Messwerte bleiben
lesbar. Score und Attribut `scale_max` stammen aus derselben Quelle und können
deshalb nicht auseinanderlaufen.

> ℹ️ Der Score ist **rein abgeleitet**: Es gibt **keine eigene Datenhaltung**
> (kein eigener Store, keine Migration des Datenbestands). Der Wert wird
> jederzeit on-read aus der letzten Wohlbefinden-Meldung berechnet und ist zu
> 100 % an die Rohdaten gekoppelt — wird die Rohmeldung geändert oder gelöscht,
> ändert sich der Score automatisch mit.

**Eigene Bilder je Wohlbefinden-Stufe (optional)**

In den Integrations-Optionen (Schritt „Wohlbefinden-Bilder") **oder im
Admin-Bereich des Panels** (Einstellungen → Wohlbefinden-Bilder) kann je Key ein
eigenes PNG/JPG/WebP hinterlegt werden. Akzeptiert werden:

- eine Datei unter `/config/www/` als reiner Dateiname (`stufe1.png` → `/local/stufe1.png`),
- ein absoluter Pfad (`/local/wellbeing/stufe1.png`),
- eine HTTP(S)-URL,
- ein Base64-Data-URI für PNG/JPEG/WebP.

Karte und Panel zeigen das Bild automatisch statt des Emojis; ohne Bild bleibt
das Emoji. Ungültige Pfade/Endungen werden serverseitig verworfen.

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
- `button.…_undo_last_drink` — **voidet** die letzte aktive Getränkebuchung
  (Undo). Der Eintrag bleibt im Verlauf erhalten und ist dort wiederherstellbar;
  für Blutdruck und Wohlbefinden stehen Undo/Verlauf im Panel bzw. in der Karte
  bereit.
- `button.…_save_measurement` — übernimmt die drei Number-Eingaben
  (`new_reading_systolic/diastolic/pulse`) als neue Blutdruckmessung und leert
  die Eingabefelder.
- `button.…_report_very_bad` … `report_excellent` — Wohlbefinden-Meldung: setzt
  den Select auf den Status und den Zeitstempel-Sensor (zehn Stufen).

**Select: kontinuierlicher Gesundheitszustand**

- `select.…_wellbeing` — „Wohlbefinden" mit 10 Stufen (Sehr schlecht → Ausgezeichnet).
  Das ist die kontinuierliche Darstellung des Gesundheitszustands: Der
  HA-Verlaufsgraph zeigt ihn als Balken-/Timeline-Darstellung, mushroom
  bietet `custom:mushroom-select-card`. Attribute: `emoji`, `reported_at`,
  `history_json` (letzte 10 Meldungen), `score` und `scale_max` (10).
  Service-Aufrufe nutzen die Roh-Keys
  (`very_bad`, `awful`, `bad`, `poor`, `okay`, `mixed`, `good`, `very_good`,
  `great`, `excellent`) oder `score: 1…10`. Für die direkte Zahleneingabe
  ohne UI gibt es zusätzlich `number.…_wellbeing_input` (1–10).

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
- `number.…_wellbeing_input` — Wohlbefinden als Zahl **1–10** (1 = sehr
  schlecht … 10 = ausgezeichnet). Eine Eingabe meldet denselben Status wie
  Select und Melden-Buttons, sodass Verlauf und `wellbeing_score` konsistent
  bleiben.

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
- **Update auf v0.14.0 (Verlauf/Void/Restore, Audit-Log, Backup v2, i18n,
  Erinnerungen, Options-Wizard, Rückdatieren):** Der Store wird beim Start
  automatisch auf **Schema v4** migriert (`id`, `created_at`, `voided_at`/
  `voided_by`/`void_reason`, `audit_log`, `wellbeing_entries`). Bestehende
  Getränke-/Messwerte und die Wohlbefinden-Historie bleiben erhalten; die
  Migration ist idempotent. **Backups** werden als **v2** geschrieben (inkl.
  Retention-Archiv und Zählern); **v1-Backups bleiben lesbar** und werden beim
  Restore migriert. **Löschen ist jetzt Void:** Einträge werden markiert, nicht
  entfernt, und bleiben wiederherstellbar. `remove_last_entry` **voidet**
  (kein Hard-Delete mehr). Der CSV-Export enthält standardmäßig nur aktive
  Einträge. **Keine Änderung an `unique_id`s, Entity-IDs oder Config-Entry-`data`.**
  Die Recorder-Langzeitstatistik wird bei Korrekturen **nicht rückwirkend**
  angepasst (dokumentierte Grenze); die Integration schreibt bei Änderungen
  keine alten Statistikwerte um.

## Laborwerte (Blutwerte)

Die vierte Datendomäne neben Trinken, Blutdruck und Wohlbefinden: **Laborwerte**
aus Blut- und Urinbefunden — strukturiert, mit Referenzbereichen und ohne
manuelle Entity-Pflege. Der Katalog umfasst **29 Marker in 9 Kategorien**:

| Kategorie | Marker (Auswahl) |
|---|---|
| Leber | ALT (GPT), AST (GOT), GGT, Bilirubin gesamt, Gesamteiweiß |
| Niere | Kreatinin, eGFR, Harnstoff, Protein/Kreatinin-Quotient (Urin) |
| Elektrolyte | Natrium, Kalium, Calcium gesamt, Magnesium, Chlorid |
| Lipide | Gesamtcholesterin, LDL, HDL, Triglyceride |
| Schilddrüse | TSH, fT4, fT3 |
| Blutbild | Hämoglobin, Leukozyten, Thrombozyten |
| Entzündung/Immunsystem | CRP, BSG |
| Verdauung | Lipase, Amylase |
| Medikamentenspiegel | Tacrolimus (Talspiegel) |

Zusätzlich gibt es die Kategorie **„Sonstige"** für **eigene Marker**. Die legt
man pro Person im **Admin-Bereich des Panels** an (Name, Einheit, Kategorie,
Referenzbereich, optional eine alternative Einheit mit Umrechnungsfaktor);
dort lassen sich auch die Referenzbereiche der Katalog-Marker überschreiben und
einzelne Kategorien ausblenden.

Werte werden intern in der **kanonischen Einheit** des Markers gespeichert.
Wird ein Wert in einer bekannten Alternativ-Einheit erfasst, rechnet die
Integration um (z. B. `mg/dL` → `µmol/L`); der eingegebene Wert bleibt als
`reported_value`/`reported_unit` nachvollziehbar. Bei Markern mit
Verwechslungsgefahr (z. B. Protein/Kreatinin-Quotient: `g/g` vs. `mg/g`) ist
`unit` deshalb Pflicht. Ein optionales `report_ref` (Link oder externe ID des
Laborberichts, **max. 500 Zeichen**) verweist auf den Befund — die Integration
ruft die Referenz **nie selbst auf**.

> ⚠️ Die Integration klassifiziert nicht medizinisch und diagnostiziert nicht —
> Referenzbereiche sind typische Erwachsenen-Richtwerte, keine klinische Norm.
> Bitte individuell in den Settings anpassen.

### Laborwert-Entities

- **Ein Sensor je Katalog- und Custom-Marker** — Entity-ID aus dem englischen
  Markernamen (Katalog) bzw. dem vergebenen Namen (Custom), z. B.
  `sensor.…_creatinine` oder `sensor.…_crp`, mit
  `state_class: measurement`; Zustand = letzter aktiver Wert in der kanonischen
  Einheit. Attribute: `ts`, `category`, `ref_min`, `ref_max`, `in_range`.
  Gelöschte (voided) Werte erscheinen nicht als Zustand; der stabile
  `unique_id`-Suffix lautet `lab_<marker>`.
- **Ein Warn-Binary je Kategorie** — `binary_sensor.…_<category>_warning`
  (z. B. `…_liver_warning`, `…_kidney_warning`; ohne „Sonstige"),
  `device_class: problem`: `on`, sobald mindestens ein aktiver Marker der
  Kategorie außerhalb seines Referenzbereichs liegt.

### Services: Laborwerte erfassen und korrigieren

```yaml
action: health_o_mat.add_lab_value
data:
  person: "Caro"            # optional — ohne Angabe die einzige konfigurierte Person
  marker: "alt"             # Katalog-Key oder eigener Marker-Key
  value: 32.0
  unit: "U/L"               # optional — Default ist die kanonische Einheit
  ts: "2026-10-31T08:00:00" # optional — leer = jetzt
  report_ref: "https://example.com/laborbericht/123"  # optional, max. 500 Zeichen
```

- `marker` akzeptiert deutsche Laborsynonyme (`gpt` → `alt`, `got` → `ast`,
  `gamma_gt` → `ggt`). Unbekannte Marker werden mit
  `ServiceValidationError` abgelehnt und **nie** automatisch als Custom-Marker
  angelegt.
- `ts` folgt derselben Regel wie die übrigen Schreib-Services (ISO 8601, leer =
  jetzt, höchstens 5 Minuten in der Zukunft).

```yaml
action: health_o_mat.remove_last_lab_value
data:
  person: "Caro"   # optional — ohne Angabe die einzige konfigurierte Person
  marker: "alt"    # letzter aktiver Wert genau dieses Markers
```

`remove_last_lab_value` **voidet** den letzten aktiven Wert des Markers (kein
Hard-Delete); der Eintrag bleibt im Verlauf wiederherstellbar.

### Laborwerte-Karte (Custom Card)

Die Integration liefert eine eigene Lovelace-Karte mit:

- Kategorie-Reiter mit allen sichtbaren Kategorien,
- je Marker Wert + Einheit, **In-Range-Badge**, optional eine Sparkline (Trend)
  und der Zeitpunkt der letzten Erfassung,
- Bericht-Link aus `report_ref`,
- ein Eingabeformular (Marker, Wert, Einheit, Zeitpunkt, Bericht-Link/ID).

```yaml
type: custom:health-o-mat-labs-card
entry_id: <config-entry-id>   # optional — ohne Angabe erscheint eine Personenauswahl
```

Die Karte wird beim Setup automatisch als Lovelace-Ressource registriert
(idempotent) — kein manuelles Hinzufügen nötig. Alle Schlüssel sind optional:
`person_mode` (`fixed` | `selector`), `person_filter`, `default_person`,
`show_categories` (Auswahl/Reihenfolge der Kategorien), `show_trend`,
`allow_manual_entry` und `show_disclaimer`; ohne Angabe sind Trend, Eingabe und
Disclaimer aktiv. Die Karte ist unabhängig vom Panel; das Panel zeigt die
Laborwerte als vierten Tab (mit Kategorie-Wischgeste).

### Migration & Export

- **Store-Schema v4 → v5:** Beim Update ergänzt die Migration je Person die
  Liste `lab_readings` — automatisch und idempotent, bestehende Daten bleiben
  unverändert. Ein manueller Schritt ist nicht nötig.
- **Backup v3** enthält Laborwerte und die Labor-Optionen (eigene Marker,
  Referenz-Overrides, ausgeblendete Kategorien); ältere Backups bleiben lesbar.
- **CSV-Export/-Import:** Datensatz `lab_values` (Datei
  `health_o_mat_labvalues_<Person>_<YYYYMMDD-HHMM>.csv`). `all` schließt
  Laborwerte mit ein.

## Services

Alle Schreib-Services (`add_drink`, `add_blood_pressure`, `set_wellbeing`,
`add_lab_value`) akzeptieren ein optionales **`ts`** (ISO 8601, z. B.
`2026-10-24T18:30` oder mit Offset). Leer = jetzt. Werte höchstens 5 Minuten in
der Zukunft und nicht vor 1900 werden akzeptiert; naive Zeitstempel gelten als
lokale Zeit. Ohne `person` wird die einzige konfigurierte Person verwendet.

```yaml
action: health_o_mat.add_drink
data:
  person: "Caro"
  amount_ml: 250
  drink_type: "Kaffee"
  ts: "2026-10-24T18:30:00+02:00"   # optional; leer = jetzt

action: health_o_mat.add_blood_pressure
data:
  person: "Caro"
  systolic: 124
  diastolic: 82
  pulse: 64
  ts: "2026-10-24T08:15:00"          # optional

action: health_o_mat.set_wellbeing
data:
  person: "Caro"
  status: "good"   # very_bad | awful | bad | poor | okay | mixed | good | very_good | great | excellent
  # ODER: score: 7  (1–10)
  # optional: ts

# Undo: voidet die letzte aktive Buchung (kein Hard-Delete)
action: health_o_mat.remove_last_entry
data:
  person: "Caro"
  kind: "drinks"   # drinks (Default) | blood_pressure | wellbeing

# Einzelnen Eintrag voiden/wiederherstellen (ID aus dem Verlauf)
action: health_o_mat.void_entry
data: { person: "Caro", kind: "drinks", id: "3f2b8c1e-0a4d-4f5e-9a76-1b2c3d4e5f60" }

action: health_o_mat.restore_entry
data: { person: "Caro", kind: "drinks", id: "3f2b8c1e-0a4d-4f5e-9a76-1b2c3d4e5f60" }

# nur Admin
action: health_o_mat.export_csv
data: { person: "Caro", dataset: "all" }   # drinks | blood_pressure | lab_values | all

action: health_o_mat.import_csv
data: { person: "Caro", filename: "health_o_mat_drinks_Caro_20261014-1200.csv" }
# optional: dataset: drinks | blood_pressure | lab_values | all (default: all = auto-detect)

action: health_o_mat.backup

# Backup kontrolliert zurückspielen (Admin-only; vorher Dry-Run)
action: health_o_mat.restore_backup
data:
  filename: "health_o_mat_backup_20261024-120000.json"
  mode: "merge"        # merge (Default) | replace
  dry_run: true

action: health_o_mat.weekly_report
data: { person: "Caro" }   # leer = jede Person erhält einen Bericht
```

`remove_last_entry` behält seinen Namen als **Kompatibilitäts-Alias**, hat aber
**Void-Semantik**: Der Eintrag wird markiert und bleibt im Verlauf
wiederherstellbar. `void_entry`/`restore_entry` benötigen `kind` und die `id`
aus dem Panel-Verlauf (WS `health_o_mat/list_history`). `set_wellbeing` ist im
Abschnitt [Wohlbefinden melden (Service)](#wohlbefinden-melden-service)
ausführlich beschrieben — Karten-Buttons und Service nutzen denselben
Store-/Refresh-Pfad wie das Panel. Die Laborwert-Services `add_lab_value` und
`remove_last_lab_value` sind im Abschnitt
[Laborwerte](#laborwerte-blutwerte) beschrieben.

## Import & Backup

### CSV-Import

Importiert eine zuvor exportierte CSV (oder eine Datei im gleichen Format) in
die Historie einer Person:

1. Datei nach `/config/health_o_mat_import/` kopieren (Ordner bei Bedarf
   anlegen).
2. Service aufrufen:

```yaml
action: health_o_mat.import_csv
data: { person: "Caro", filename: "health_o_mat_drinks_Caro_20261014-1200.csv" }
```

Der Import ist bewusst tolerant: Semikolon-getrennt, UTF-8 mit oder ohne BOM,
`#`-Kommentarzeilen und eine fehlende/abweichende Kopfzeile werden akzeptiert.
Bestehende Einträge werden als Duplikate erkannt und übersprungen (Getränke über
Zeitstempel + Menge, Blutdruck über Zeitstempel + systolisch + diastolisch);
unlesbare Zeilen werden abgelehnt. Eine Notification meldet das Ergebnis als
`imported / skipped / rejected`.

### Backup (JSON-Voll-Export)

```yaml
action: health_o_mat.backup
```

Schreibt ein versioniertes JSON-Backup **aller Personen und Datensätze** (alle
Zeiträume) nach `/config/health_o_mat_export/` mit Zeitstempel-Dateinamen
(`health_o_mat_backup_<YYYYMMDD-HHMMSS>.json`). **Format v2** enthält zusätzlich
das **Retention-Archiv**, die Schema-Stufe, Personen-Namen und Zähler
(gesamt/aktiv/gelöscht). **v1-Backups bleiben lesbar** und werden beim Restore
migriert; neuere/unbekannte Versionen werden mit klarer Meldung abgelehnt.
Der Service ist **nur für HA-Administratoren** verfügbar.

### Restore (Backup zurückspielen)

Der Restore ist **verfügbar** und bewusst kontrolliert:

1. Backup-Datei nach `/config/health_o_mat_import/` kopieren oder eine
   bereits geschriebene Backup-/Pre-Restore-Datei aus
   `/config/health_o_mat_export/` verwenden (kein Browser-Upload).
2. **Dry-Run** ausführen — er plant nur und schreibt nichts (auch für Replace
   ohne Bestätigung).
3. Bei Bedarf **Merge** (Default) oder **Replace** wählen und anwenden.

```yaml
# 1) Probelauf: zeigt added/updated/skipped/conflicts/errors/persons
action: health_o_mat.restore_backup
data:
  filename: "health_o_mat_backup_20261024-120000.json"
  mode: "merge"
  dry_run: true

# 2) Merge: ergänzt Einträge, Duplikate werden übersprungen
action: health_o_mat.restore_backup
data:
  filename: "health_o_mat_backup_20261024-120000.json"
  mode: "merge"

# 3) Replace: leert zuerst den gewählten Scope — Bestätigung "REPLACE" Pflicht
action: health_o_mat.restore_backup
data:
  filename: "health_o_mat_backup_20261024-120000.json"
  mode: "replace"
  confirm: "REPLACE"
```

- **Teil-Restore:** `persons` (Quell-Slug, Quell-Entry-ID oder Ziel-Entry-ID),
  `datasets` (`drinks` / `blood_pressure` / `wellbeing`), `from`/`to` (ISO,
  inklusiv auf `ts`; naive Werte gelten als lokale HA-Zeitzone).
- **Mehrere Quellen → ein Ziel:** `person_map` darf mehrere Backup-Personen
  auf denselben Ziel-Entry abbilden. Replace sammelt dann alle Quell-Records,
  dedupliziert sie und leert den Ziel-Scope genau einmal (kein Datenverlust).
- **Personen-Mapping:** `person_map: {<Quelle>: <Ziel-Entry-ID>}`. Unbekannte
  Personen werden **nie automatisch angelegt** — ohne eindeutige Zuordnung
  bricht der Restore mit einer Meldung ab.
- **Sicherheitsbackup:** Vor jedem echten Restore entsteht automatisch ein
  Pre-Restore-Backup im Export-Ordner. Der Restore ist atomar (ein Save,
  In-Memory-Rollback bei Fehler).
- **Admin-only:** Service und WebSocket-Kommando sind serverseitig auf
  HA-Administratoren beschränkt; das Panel bietet eine Admin-Restore-Karte mit
  Dateiauswahl, Modus, Filtern, Dry-Run und Bestätigung.
- **Audit:** Importierte Audit-Historie wird standardmäßig **nicht** übernommen;
  stattdessen werden neue `restore_backup`-Ereignisse geschrieben
  (`restore_audit: true` nur für Experten).

### Dateien & Datenschutz

Beide Richtungen nutzen ausschließlich private Verzeichnisse:

- `/config/health_o_mat_import/` — Import-/Restore-Quelle
- `/config/health_o_mat_export/` — CSV-Exporte, JSON-Backups und
  Pre-Restore-Sicherheitsbackups

Dateien werden **nie** nach `/config/www/` geschrieben (dort wären sie über den
HA-Webserver öffentlich erreichbar). Diese Ordner aus jedem öffentlichen Share
heraushalten.

## Löschen, Audit & Datenschutz

**Bewusst kein Hard-Delete in der UI.** Löschen bedeutet immer **Void**: Der
Eintrag wird mit `voided_at`/`voided_by`/`void_reason` markiert, zählt nicht
mehr in Auswertungen (heute/gestern, Trends, Streak, BD-Ø, Koffein, Lifetime,
Sensoren, CSV) und bleibt über **Restore** wiederherstellbar. Auch
`remove_last_entry` voidet nur.

- **Audit-Log:** Add, Void, Restore, Import und Restore-Backup erzeugen ein
  append-only-Ereignis mit Zeit, Aktion, Ziel und Actor
  (HA-User-ID, bei Automationen leer). Es enthält **keine vollen
  Gesundheitswerte**, nur Metadaten. Default-Cap: **1000 Ereignisse pro Person**;
  im Panel-Admin ist `0` = **unbegrenzt** (bzw. ein positiver Wert) einstellbar.
  Beim Kappen bleibt ein `audit_pruned`-Summary-Ereignis nachvollziehbar.
- **Vollständige Entfernung:** Nur **manuell außerhalb der UI** über die
  Store-Datei bzw. die Integration (z. B. Entry löschen und Store-Datei
  entfernen). Das Panel bietet dafür keinen Knopf.
- **DSGVO-Hinweis/Restrisiko:** Void/Restore + Audit-Log sind die bewusste
  Datenschutz-Abwägung. Gelöschte (voided) Einträge wachsen ohne Hard-Delete und
  bleiben im Backup erhalten; die vollständige Datenentfernung ist ein
  dokumentierter manueller Vorgang. Vor einer öffentlichen 1.0 wird das erneut
  bewertet.
- **Recorder:** Die HA-Langzeitstatistik wird bei Korrekturen **nicht
  rückwirkend** angepasst — sie bleibt eine dokumentierte Grenze. Der CSV-Export
  enthält standardmäßig nur aktive Einträge; das Backup enthält Audit- und
  voided-Einträge.

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
  **Wohlbefinden-Score** als Badge (z. B. „4 / 10") und eine **kleine Sparkline**
  der letzten 14 Meldungen. Die Karte bleibt damit eine einbettbare
  Kompaktanzeige — **kein** Panel-Ersatz
- ↩️ **Quick-Drink-Buttons + Undo** — feste Menge buchen oder die letzte
  Buchung **voiden**; Undo gibt es für Getränke, Blutdruck **und** Wohlbefinden
- 🕒 **Rückdatieren** — Getränke-, Blutdruck- und Wohlbefinden-Eingaben haben
  ein Zeitpunktfeld (`datetime-local`); **leer = jetzt**
- 📜 **Optionaler Verlauf** — pro Typ die letzten **5** Einträge, inkl.
  Inline-Löschen mit Bestätigung und Wiederherstellen (`show_history`, Default
  **aus**). Die vollständige Ansicht bleibt das Panel

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
| `show_wellbeing_input` | bool | `true` | Die zehn Wohlbefinden-Buttons. |
| `show_wellbeing_numeric` | bool | `true` | Zusätzliches Zahlenfeld (1–10) neben den Smileys. |
| `wellbeing_confirm` | bool | `false` | Wohlbefinden-Auswahl erst nach Klick auf **Übernehmen** melden (unabhängig von der Panel-/Server-Option `wellbeing_confirm`). |
| `show_blood_pressure_history` | bool | `true` | Blutdruck-Verlaufsgraph (systolisch/diastolisch, letzte 30 Messungen). |
| `show_history` | bool | **`false`** | Kompakter Verlauf je Typ (letzte **5** Einträge, inkl. gelöschter, damit Wiederherstellen erreichbar bleibt) mit Inline-Löschen (Void, mit Bestätigung) und Wiederherstellen. Die vollständige Historie zeigt das Panel. |
| `show_undo` | bool | `true` | Undo für Getränke, Blutdruck und Wohlbefinden (voidet den letzten aktiven Eintrag). |
| `drinks` | list[str] | alle | Keys der Quick-Drinks aus der Integration (`panel_data.quick_drinks`); unbekannte Keys werden ignoriert, leer/fehlend = alle. |
| `manual_amounts` | list[int] | `[200, 500]` | ml-Presets (1…10000); leer/fehlend = Default. |
| `allow_custom_amount` | bool | `true` | Zusätzliches freies Zahlenfeld mit Buchen-Button. |
| `quick_drinks` | list[object] | – | Legacy-Override (`[{label, ml, emoji}]`); gewinnt gegenüber `drinks` und der Integrationsliste. |

**Semantik:** `show_*=false` blendet den Block samt zugehöriger Eingaben aus.
Ein **explizit** gesetztes `show_blood_pressure_input: true` hat Vorrang vor
`show_blood_pressure: false` (die Eingabe bleibt sichtbar). Sind alle Blöcke aus,
zeigt die Karte einen lesbaren Hinweis statt einer leeren Fläche. Die
Zeitpunktfelder senden `ts` an dieselben Services wie das Panel; leere Felder
bedeuten „jetzt", die Zukunft wird abgelehnt. `show_history` ist bewusst **aus**
und lädt nur bei Bedarf die letzten 5 Einträge (inkl. gelöschter).

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
  status: "good"   # very_bad | awful | bad | poor | okay | mixed | good | very_good | great | excellent
  # ODER numerisch:
  # score: 7
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
- 🕒 **Rückdatieren** — jedes Eingabeformular hat ein Zeitpunktfeld
  (`datetime-local`) plus Schnellwahl **„Jetzt"** und **„Gestern"**; **leer =
  jetzt**, die Zukunft wird abgelehnt
- 📜 **Verlauf je Tab** — neueste zuerst, mit Filter **„Nur aktive"**
  / **„Auch gelöscht"**, Inline-**Löschen mit Bestätigung** (Void) und
  **Wiederherstellen**. Gelöschte Einträge sind sichtbar markiert und zählen
  nicht in den Auswertungen
- ↩️ **Undo für alle Typen** — Getränke, Blutdruck und Wohlbefinden
- 📈 **Wohlbefinden-Score-Chart** — im Tab „Wohlbefinden" zeigt das Panel den
  **vollständigen Verlaufs-Chart** des Scores: Zeit auf der X-Achse, Score 1–10
  auf der Y-Achse (Extremwerte 1 und 10 hervorgehoben), Zeitachse und der
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
**einem** Ort verwalten — inklusive der Schlüssel, die der Options-Wizard nicht
zeigt (`wellbeing_confirm`, `audit_limit`), als eine scrollbare Maske statt
verschachtelter Options-Schritte:

- 🎯 **Tagesziel** (mL) und **Reset-Uhrzeit** (0–23 Uhr)
- 🏷️ **Anzeigename** der Person
- 🥤 **Quick-Drink-Slots** (4, je Label/Icon/mL)
- 📖 **Getränke-Lexikon** — eine Zeile je Wort im Format `wort=Typ,ml`, mit
  Zeilen-Validierung (die Fehlermeldung nennt die betroffene Zeile)
- 🩺 **Blutdruck-Warnschwellen** (sys/dia) — wirken zur Laufzeit sofort auf den
  Blutdruck-Warn-Binary-Sensor
- 🗄️ **Aufbewahrung** (Retention in Monaten) und **`audit_limit`**
  (Audit-Log-Cap; Default **1000** Ereignisse/Person, `0` = **unbegrenzt**)
- 🧩 **Feature-Toggles pro Person** — **Trinken / Blutdruck / Wohlbefinden**
  einzeln an/aus. Ein abgeschalteter Bereich erzeugt **keine** Entities mehr
  (sie werden beim Reload entladen); `unique_id` und Historie bleiben
  **unverändert**, ein Wieder-Einschalten erzeugt dieselbe `entity_id` wieder.
  Fehlt die Auswahl (Alt-Entry), sind alle Bereiche aktiv
- ✅ **Wohlbefinden: Bestätigung vor Übernahme** (`wellbeing_confirm`, Default
  aus) — pro Person in der Panel-Admin-Ansicht (Karte „Wohlbefinden") pflegbar;
  gespeichert wird sie über denselben Einstellungs-Pfad wie die übrigen
  Optionen. Aktiv merkt sich ein Klick auf eine Stufe nur die Auswahl;
  gesendet wird sie erst mit **Übernehmen**. Die Karte hat dafür einen eigenen,
  unabhängigen Schalter gleichen Namens
- 📌 **Sidebar-Panel-Schalter** (Opt-in)
- ♻️ **Restore-Karte** — Backup-Datei aus `/config/health_o_mat_import/`
  auswählen, Modus **Merge/Replace**, Datensätze und Zeitraum filtern,
  **Dry-Run** ausführen, bei Replace `REPLACE` bestätigen und anwenden.
  Personen-Mapping ist möglich; vor dem echten Restore wird automatisch ein
  Sicherheitsbackup geschrieben
- 📄 **CSV-Export** direkt aus dem Panel anstoßen
  (`drinks` / `blood_pressure` / `all`, geschrieben nach
  `/config/health_o_mat_export/`)
- 💾 **Backup** direkt aus dem Panel auslösen (ruft den `health_o_mat.backup`-Service)
- ➕ **Person anlegen** — öffnet den Standard-HA-Config-Flow (kein eigener Dialog)
- 🗑️ **Person löschen** — nur Admin, mit **Doppelbestätigung** (die Bestätigung
  muss dem Personen-Schlüssel entsprechen). **Achtung:** Das entfernt die
  Integration samt Entities und ist **kein Hard-Delete der Gesundheitsdaten** —
  der Store wird nicht aufgeräumt. Ein Backup lässt sich inzwischen über die
  Restore-Karte zurückspielen; für vollständige Datenentfernung siehe
  [Löschen, Audit & Datenschutz](#löschen-audit--datenschutz)

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

## Sprache & Internationalisierung (de/en)

Panel, Karte, Karten-Editor und Admin-Ansicht folgen der **HA-Sprache**
(`hass.language`) — **Deutsch und Englisch** vollständig. Ein Sprachwechsel zur
Laufzeit rendert die Oberfläche neu, ohne Reload.

- **HA-nativ statt eigenem Framework:** Die UI-Texte liegen als flache Schlüssel
  im erlaubten `common`-Bereich (`component.health_o_mat.common.*`) und werden
  im Frontend über `frontend/get_translations` (`category: "common"`,
  `integration: ["health_o_mat"]`) geladen und pro Sprache gecacht.
- **Sauberer Fallback:** Eine eingebettete de/en-Fallback-Map fängt fehlende
  Übersetzungen ab; rohe `ui_…`-Keys werden **nie** angezeigt.
- **Zahlen/Datum/relative Zeit** laufen über `Intl`/`hass.locale`.
- **Entity- und Service-Übersetzungen** bleiben unverändert HA-nativ
  (`translations/de.json` / `en.json`).
- Übersetzungsbeiträge betreffen nur die `translations/*.json` — keine Logik.

## E2E-Tests (Playwright)

**Aktueller Stand:** **18 E2E-Tests** (realer HA-Docker-Stack) und **1120
Unit-Tests**; `ruff check .` und `ruff format --check .` sind clean. Der
Deep-Link des Panels (`?person=<slug>`) ist als **echter Browser-Test**
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

Zusätzlich (`tests_e2e/test_wellbeing_confirm_e2e.py`, REQ-HOM-114):

- Karten-Option `wellbeing_confirm`: Klick merkt die Stufe nur vor, der
  Bestätigungsbutton erscheint, erst dessen Klick schreibt den Wert
- Panel-Admin-Option pro Person: Checkbox speichert, der Detail-Tab meldet erst
  nach dem Bestätigungsbutton

Zusätzlich (`tests_e2e/test_history_e2e.py`, REQ-HOM-115/120):

- **Rückdatieren** über das Zeitpunktfeld: der Eintrag landet am gewählten Tag
  (z. B. „Gestern"), nicht in „Heute"
- **Void im Verlauf:** gelöschter Eintrag verschwindet aus „Heute" und ist im
  Filter **„Auch gelöscht"** sichtbar
- **Restore:** Wiederherstellen stellt den Vorher-Wert wieder her

Zusätzlich (`tests_e2e/test_i18n_e2e.py`, REQ-HOM-117):

- Panel rendert bei **en-US** englische Labels (kein roher `ui_…`-Key)
- Karte rendert bei **en-US** englische Labels

Die Karten-Konfiguration ist außerdem in `tests_e2e/test_card_config_e2e.py`
abgesichert (Sichtbarkeit der Blöcke, explizite BD-Eingabe, Wellbeing-Eingabe,
Resave der Konfiguration).

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

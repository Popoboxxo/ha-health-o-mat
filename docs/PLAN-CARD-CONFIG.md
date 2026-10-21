# Plan: Konfigurierbare Health-O-Mat-Karte (Dashboard-Einstellungen)

**Status:** umgesetzt — Branch `feat/configurable-card`, 2026-10-21
**Datum:** 2026-10-20 (Plan) · **Basis:** v0.9.0 (`9ff3414`)
**Bezug:** `docs/CONCEPT-UI.md`, `README.md` (Custom Card), REQ-HOM-011/014/113
**Vorgänger-Idee:** REQ-HOM-112 (Wohlbefinden-Score + Chart)

---

## 1. Ziel

Die mitgelieferte Lovelace-Karte (`custom:health-o-mat-card`) wird über den
**Karten-Editor im Dashboard** (visuelle „Dashboard-Einstellungen") konfigurierbar:

1. **Welche Getränke** als Schnellbuchung erscheinen (Auswahl aus den in der
   Integration konfigurierten Quick-Drinks).
2. **Welche manuellen ml-Angaben** es gibt (Preset-Buttons + freies Zahlenfeld).
3. **Blutdruck-Eingabe** (Systolisch / Diastolisch / Puls + Notiz) ein-/ausschaltbar.
4. **Wohlbefinden-Eingabe** (5 Zustände) ein-/ausschaltbar.
5. **Alle Anzeige-Blöcke** (Personenwahl, Hydration-Ring, letzter BD, letztes
   Wohlbefinden, Score-Trend, Undo) einzeln ein-/ausschaltbar.

**Nicht-Ziel:** Panel-Konfiguration (das Panel bleibt die feste App-Ansicht);
kein Dashboard-Builder, keine neue Persistenz von Gesundheitsdaten, keine
Änderung der `unique_id`s.

---

## 2. Beschlossene Entscheidungen

| # | Entscheidung |
|---|---|
| E1 | Getränke werden **aus der Integration** referenziert (Auswahl per Key), keine kartenlokale Zweitliste. Das bestehende `quick_drinks`-Override bleibt als Escape-Hatch. |
| E2 | Manuelle Mengen: **Preset-Buttons aus der Kartenkonfiguration + optionales freies Zahlenfeld**. |
| E3 | Wohlbefinden schreibt über einen **neuen öffentlichen Service** `health_o_mat.set_wellbeing` (konsistent zu den übrigen Schreibpfaden, automations­tauglich). Die bestehenden `button.*_report_*`-Entities bleiben unverändert. |
| E4 | **Auch Anzeige-Blöcke** sind ein-/ausschaltbar (nicht nur Eingaben). |
| E5 | BD-Eingabe: **Sys/Dia/Puls + optionale Notiz**. |
| E6 | **Nur die Karte** wird konfigurierbar. Im Panel muss der **Wohlbefindens-Verlauf sichtbar** sein (bereits durch REQ-HOM-112 vorhanden — wird verifiziert, ggf. leicht erweitert). |

---

## 3. Konfigurationsschema (Karte)

Alle Schlüssel sind **optional**. Die **Anzeige-Blöcke** bleiben per Default
unverändert (an); die **neuen Eingabe-Blöcke** (manuelle Mengen, BD-Eingabe,
Wohlbefinden-Eingabe) sind per Default **an** — bestehende Karten erhalten sie
beim Update. Das ist eine **bewusste Abweichung** von „Verhalten unverändert"
und wird im Release v0.10.0 unter „✨ New features" geführt. Leere
Getränkeauswahl = alle konfigurierten Getränke.

```yaml
type: custom:health-o-mat-card
entry_id: <optional>            # bestehend: Person binden
person: <optional>              # bestehend: Service-Anker

# --- Anzeige-Blöcke (E4) ---
show_person: true               # Personen-Dropdown im Kopf
show_hydration: true            # Ring + Tageswerte + Pace/Serie/Koffein
show_blood_pressure: true       # letzte Messung + WHO-Kategorie + Warnung
show_wellbeing: true            # letztes Wohlbefinden + Score + Trend

# --- Eingabe-Blöcke ---
show_drinks: true               # Quick-Drink-Buttons
show_manual_amounts: true       # Preset-Buttons + freies Feld
show_blood_pressure_input: true # Sys/Dia/Puls/Notiz + Speichern
show_wellbeing_input: true      # 5 Zustands-Buttons
show_undo: true                 # Undo (Getränk)

# --- Getränke-Auswahl (E1) ---
drinks: ["slot_0", "slot_2"]    # Keys der Integrations-Quick-Drinks; leer/fehlt = alle
# Bestehendes Override bleibt (Legacy, gewinnt gegenüber `drinks`):
# quick_drinks: [{label: "Kaffee", ml: 250, emoji: "☕"}]

# --- Manuelle Mengen (E2) ---
manual_amounts: [200, 330, 500] # ml-Presets; leer/fehlt = Default [200, 500]
allow_custom_amount: true       # freies Zahlenfeld + Buchen
```

**Semantik**
- `show_*=false` blendet den Block vollständig aus (inkl. zugehöriger Eingaben).
- `show_blood_pressure=false` blendet Anzeige **und** (falls `show_blood_pressure_input`
  nicht explizit `true`) die Eingabe aus — die Eingabe hat aber Vorrang, wenn
  sie explizit aktiviert ist.
- Unbekannte/ungültige Werte → Defaults (defensiv, nie Render-Crash).
- `drinks` referenziert die **Keys** der Integrations-Quick-Drinks (`slot_0` …;
  Defaults: `glas_wasser`, `flasche_wasser`, `kaffee`, `saft`). Unbekannte Keys
  werden ignoriert; leere Schnittmenge → alle (kein leerer Zustand).

---

## 4. Backend-Änderungen

### 4.1 `panel_data` erweitern (additiv)
`ws_api.build_panel_data()` liefert zusätzlich:

```python
"quick_drinks": _quick_drinks(entry),  # [{key,label,ml,icon}]
```

Grund: Karte **und** Editor müssen die konfigurierten Getränke kennen, ohne
admin-only `get_settings`. `_quick_drinks()` existiert bereits (Options +
Defaults, frische Kopien). Keine bestehenden Keys ändern.

### 4.2 Neuer Service `health_o_mat.set_wellbeing` (E3)
- **Parameter:** `person` (optional, wie bei allen Services), `status`
  (Pflicht, einer der `WELLBEING_STATES`-Keys).
- **Handler:** validiert den Status gegen `const.WELLBEING_STATES`, ruft
  `store.set_wellbeing(entry_id, status, now)` und `signal_refresh(entry_id)`.
  Ungültiger Status → `ServiceValidationError`.
- **Dateien:** `__init__.py` (Registrierung, analog `add_drink`/`add_blood_pressure`),
  `services.yaml` (Name/Beschreibung/Felder, deutsch), Service-Übersetzungen
  (de/en, falls vorhanden), `tests/`.
- **Kein Zweitweg:** derselbe Store-/Refresh-Pfad wie das WS-Kommando
  `health_o_mat/set_wellbeing` (Panel). Das WS-Kommando bleibt bestehen.

### 4.3 Buchung mit Getränketyp (Bugfix)
`_book()` in der Karte sendet künftig zusätzlich `drink_type` (Label des
Getränks). Ohne das landet jede Buchung als „Eigen" und der Breakdown
(Wasser/Kaffee/…) ist falsch. Für manuelle Mengen bleibt `drink_type="Eigen"`.

---

## 5. Frontend-Änderungen

### 5.1 Karte (`www/health-o-mat-card.js`)
- `setConfig`: neue Keys normalisieren (Defaults, Typen, Listen bereinigen);
  keine Exception bei Unfug.
- `_body()`: rendert Blöcke abhängig von den `show_*`-Flags; übrig bleibender
  Leerzustand → verständlicher Hinweis („Keine Blöcke aktiviert").
- **Getränke:** `_quickDrinks()` filtert die Integrationsliste (`panel_data.quick_drinks`)
  nach `drinks`-Keys; Legacy-Override gewinnt. Buchung sendet `drink_type`.
- **Manuelle Mengen:** Preset-Buttons (aus `manual_amounts`) + optionales
  Zahlenfeld mit Buchen-Button; Validierung (>0, Obergrenze wie Backend).
- **BD-Eingabe:** Felder Sys/Dia/Puls/Notiz + Speichern; nutzt den bestehenden
  Service `health_o_mat.add_blood_pressure` (`note` wird unterstützt);
  Bereichsvalidierung (Sys/Dia 40–260, Puls 20–250), Fehleranzeige inline.
- **Wohlbefinden-Eingabe:** 5 Buttons aus der (server-gelieferten) Skala;
  ruft den neuen Service `health_o_mat.set_wellbeing`; aktiver Zustand markiert.
- **Aktionen** (Buchen/Speichern/Melden) setzen den Busy-Zustand und laden die
  Daten neu (bestehendes Muster).
- Einheitliche Optik über HA-CSS-Variablen; mobiltauglich.
- Barrierefreiheit: Labels, `aria-label`, Tastaturbedienung der Buttons.

### 5.2 Editor (`HealthOMatCardEditor`)
- Lädt Personen (bestehend) **und** für die gewählte Person `panel_data.quick_drinks`
  (für die Getränke-Mehrfachauswahl).
- UI:
  - Person + Service-Anker (bestehend)
  - Checkbox-Gruppen „Anzeige" (4) und „Eingabe & Aktionen" (5)
  - Getränke-Auswahl: Checkbox-Liste der konfigurierten Getränke (Label + ml);
    „Alle" als Default-Zustand
  - Manuelle Mengen: Liste mit Add/Remove (Zahl in ml) + Toggle „freies Feld"
- Jede Änderung feuert `config-changed` (bestehendes Muster).
- Defensiv: fehlende `panel_data`/Personen → Editor bleibt bedienbar, Hinweis.

**Abweichung (umgesetzt):** Der Editor gruppiert **alle neun** `show_*`-Schalter
als „Anzeige" (4: `show_person`, `show_hydration`, `show_blood_pressure`,
`show_wellbeing`) und „Eingabe & Aktionen" (5: `show_drinks`,
`show_manual_amounts`, `show_blood_pressure_input`, `show_wellbeing_input`,
`show_undo`). Der Plan nannte hier ursprünglich „6/5" — die 4/5-Gruppierung ist
die umgesetzte und getestete Variante
(`tests/test_card_js.py::test_card_editor_renders_all_nine_flags_in_two_groups`).

---

## 6. Panel (E6)

- Der Wohlbefindens-Tab zeigt bereits den **Score-Verlauf** (REQ-HOM-112).
  **Verifikation** im E2E: Chart vorhanden, Y-Achse 1–5, Verlauf sichtbar.
- **Umgesetzt:** zusätzlich die **Verlaufsliste** (Zeitpunkt, Emoji, Label und
  Score — letzte 20 Meldungen) unter dem unveränderten Chart.
- **Keine** neuen Panel-Konfigurationsschalter in dieser Iteration.

---

## 7. Tests

- **Python**
  - `panel_data` enthält `quick_drinks` (Keys/Labels/ml) und bleibt sonst
    byte-kompatibel (bestehende Keys unverändert).
  - `set_wellbeing`-Service: gültig → Store + Refresh; ungültig → 
    `ServiceValidationError`; Person-Auflösung wie bei den anderen Services.
  - Services-yaml/Translations-Konsistenz (sofern getestet).
- **JS-Analyse** (`tests/test_card_js.py`, Muster bestehend)
  - Config-Defaults/Backward-Compat; `show_*`-Flags im Rendering;
  - Getränke-Filter nach Keys; `drink_type` wird gesendet;
  - manuelle Mengen + freies Feld; BD-/Wohlbefinden-Eingabe ruft die richtigen
    Services; Editor rendert alle Felder und feuert `config-changed`.
- **E2E (Playwright, umgesetzt)**
  - Card auf einer Test-View mit verschiedenen `show_*`-Kombinationen rendern;
  - BD-Eingabe + Wohlbefinden-Eingabe end-to-end (Service-Aufruf, UI-Update).
  - Umgesetzt als `tests_e2e/test_card_config_e2e.py` (**7 Tests**): alle Blöcke
    aus, BD-Anzeige aus, explizite BD-Eingabe, Hydration aus,
    Konfigurations-Neuspeichern, BD-Eingabe schreibt, Wohlbefinden-Eingabe
    schreibt und aktualisiert die UI.

---

## 8. Risiken & Gegenmaßnahmen

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Backward-Compat der Karte | Bestehende Dashboards brechen | Alle Keys optional, Unbekanntes → Default; Anzeige-Defaults unverändert; neue Eingabe-Blöcke bewusst per Default an (dokumentiert, v0.10.0 „New features"); Tests |
| `quick_drinks`-Keys ändern sich | Auswahl verliert Getränke | Keys stabil halten (`slot_N`/Default-Keys); unbekannte Keys ignorieren, Fallback „alle" |
| Doppelte Datenquelle (Options vs. Karte) | Verwirrung | E1: nur Referenzierung; Override klar als Legacy dokumentiert |
| Service-Missbrauch (Wohlbefinden) | Falsche Werte | Status-Validierung gegen `WELLBEING_STATES`; `ServiceValidationError` |
| Cache-Buster/ES-Import | Weiße Karte nach Release | `manifest.version` + alle `?v=` **gemeinsam** bumpen; Test erzwingt es |
| Karten-Editor ohne Daten | Leere Getränkeliste | Defensiver Zustand + Hinweis; Auswahl „alle" |
| Scope-Creep | „Dashboard-Builder" | Strikt die 5 Ziele; keine freie Grid-Konfiguration |

---

## 9. Release

- **MINOR → v0.10.0** (neue Features, nicht breaking; Anzeige-Defaults
  unverändert, neue Eingabe-Blöcke per Default an — bewusste Abweichung von
  „Verhalten unverändert", im Release unter „✨ New features").
- `manifest.version` **und** alle `?v=`-Cache-Buster in den JS-Modulen
  **gemeinsam** bumpen (Test `test_every_version_query_matches_manifest_version`).
- Release-Dreiklang: Commit → Tag `v0.10.0` → stabiles GitHub-Release
  (Summary / ✨ New features / 🐛 Bug fixes / 💥 Breaking changes: keine /
  Full Changelog).
- E2E-Workflow läuft bei `custom_components/**`-Änderungen automatisch mit.

**Stand 2026-10-21:** Die Umsetzung ist **ohne Versions-Bump** erfolgt —
`manifest.version` und alle `?v=`-Cache-Buster bleiben unverändert. Der
Release-Dreiklang (v0.10.0) folgt separat.

---

## 10. Bestätigte Entscheidungen (ehemals offene Punkte)

1. **`manual_amounts`-Default:** `[200, 500]` — bestätigt. `allow_custom_amount`
   Default `true` (freies Zahlenfeld an). Beides ist im Normalisierer der Karte
   umgesetzt (`DEFAULT_MANUAL_AMOUNTS`, `toBool(..., true)`).
2. **`show_blood_pressure_input` bei `show_blood_pressure: false`:** Die Eingabe
   ist ausgeblendet, **außer** sie ist explizit `true` gesetzt — dann gewinnt sie.
   Bestätigt; die Information, welche Keys explizit gesetzt wurden, bleibt im
   Normalisierer erhalten.
3. **Notizfeld:** optionales, einklappbares `<details>`-Feld, **Default zu** —
   bestätigt (die Karte bleibt kompakt).
4. **Panel-Verlauf:** Der Score-Chart bleibt unverändert; **zusätzlich** wurde die
   Verlaufsliste ergänzt (letzte 20 Meldungen mit Zeitpunkt, Emoji, Label und
   Score). Reine Anzeige, keine neuen Panel-Schalter.
5. **E2E-Card-Test:** **jetzt gebaut** — `tests_e2e/test_card_config_e2e.py`
   (Playwright, 7 Tests): alle Blöcke aus, BD-Anzeige aus, explizite BD-Eingabe,
   Hydration aus, Konfigurations-Neuspeichern, BD-Eingabe schreibt,
   Wohlbefinden-Eingabe schreibt und aktualisiert die UI. Kein Folgeschritt
   nötig.

# E2E-Verifikation — Wohlbefinden-Score (REQ-HOM-112) — **finaler Code-Stand**

**Instanz:** `ha-test` (Headless HA in Docker) · **HA-Version:** 2026.9.1 · **Zustand:** RUNNING
**Branch:** `feat/wellbeing-score` (Basis `main` @ `e93c783`) · **Sync:** 2026-10-20 01:26:44 (+02:00)
**Testzeitraum:** 2026-10-20 01:24 → 2026-10-20 01:48 (+02:00)

> **Zweck dieses Laufs:** *Finale* E2E-Verifikation des **endgültigen** Code-Stands.
> Der Vorlauf hatte den **Chart-Marker** noch als „letzter Serienpunkt" bestimmt;
> der finale Stand markiert den aktuellen Wert **explizit** über `isCurrent`
> (ohne aktuellen Wert wird **nichts** hervorgehoben, die Zusammenfassung lautet
> dann „letzter Wert N von M"). **Alle Belege in diesem Bericht stammen aus dem
> finalen Working Tree** — die md5-Hashes der JS-Dateien in B.0 belegen, dass
> Instanz, Browser und Repo denselben Stand hatten.
>
> **Kernbefund:** Kopfzeile, `aria-label` und `point-current` nennen **denselben,
> aktuellen** Score. Der letzte Historienpunkt (per Store-Semantik der
> **abgelöste** Status) weicht **davon ab** — genau der Kontrast, der den
> alten Bug sichtbar machte.

---

## A) Sync & Grundverifikation

### A.1 Sync (wörtliche Ausgabe)

```
$ cd /home/hermes/ha-test && bin/sync /home/hermes/repos/ha-health-o-mat
2026-10-20T01:26:44+02:00
== sync health_o_mat  (/home/hermes/repos/ha-health-o-mat) ==
== HA neu starten ==
 Container ha-test Restarting
 Container ha-test Started
== Warten auf API (200 mit Token) ==
HA bereit (nach ~6s)

== Setup-Fehler im Log? ==
ha-test  | 2026-10-20 01:26:30.320 ERROR (MainThread) [homeassistant.components.http.data_validator] Data does not match schema: required key not provided at 'client_id'
ha-test  | 2026-10-20 01:26:32.619 ERROR (MainThread) [homeassistant.components.http.data_validator] Data does not match schema: required key not provided at 'client_id'
RC=0
2026-10-20T01:26:55+02:00
```

Nur die eigene Domain wurde gesynct (`custom_components/health_o_mat`).
`bin/reset` wurde **nicht** ausgeführt, `bin/set-language` wurde **nicht**
ausgeführt, es wurden **keine** Config-Entries/Personen gelöscht, **keine**
`unique_id` geändert und **keine** Tokens kopiert oder committet
(`.ha-state/token.json` bleibt lokal, `chmod 600`).

> **Die beiden ERROR-Zeilen stammen NICHT aus der Integration**, sondern aus
> der **Token-Erneuerung dieses Laufs** (siehe A.0): das Refresh-Token der
> geteilten Instanz war abgelaufen, der erste Erneuerungsversuch über
> `POST /auth/token` mit `grant_type=refresh_token` wurde von HA mit
> `{"error":"invalid_request"}` abgewiesen (siehe wörtliches Zitat in A.0).
> Die beiden Logzeilen stammen von den **Auth-Endpunkt-Handshakes** (Login-Flow
> ohne `client_id`), also vom HA-Frontend-/Auth-Layer, **nicht** vom
> `health_o_mat`-Setup. Beide Zeitstempel liegen **vor** dem Neustart
> (01:26:30 / 01:26:32 < 01:26:44 Sync-Neustart).

### A.0 Token-Erneuerung (Hinweis, kein Eingriff in die Instanz)

Das Refresh-Token der geteilten Instanz war **abgelaufen** (`expires_at` in der
Vergangenheit) und wurde vom HA-Refresh-Endpoint abgewiesen:

```
$ curl -sS -X POST http://127.0.0.1:8123/auth/token \
    -d grant_type=refresh_token -d refresh_token="$REFRESH"
{"error":"invalid_request"}
```

Erneuerung über den **regulären HA-Login-Flow** (derselbe Weg wie
`bin/provision`), nur lokal in `.ha-state/token.json` geschrieben:

```
$ curl -sS -X POST http://127.0.0.1:8123/auth/login_flow \
    -H 'Content-Type: application/json' \
    -d '{"client_id":"http://127.0.0.1:8123/","handler":["homeassistant",null],"redirect_uri":"http://127.0.0.1:8123/"}'
{"type":"form","flow_id":"f26e519c13a6632164a7f4b99dc5457a", …}

$ curl -sS -X POST "http://127.0.0.1:8123/auth/login_flow/$FID" \
    -H 'Content-Type: application/json' \
    -d "{\"client_id\":\"http://127.0.0.1:8123/\",\"username\":\"healthbot\",\"password\":\"$PW\"}"
{"type":"create_entry","flow_id":"f639ef7514343cfb5f755455fdcd225f", …,
 "result":"3aadc4c161914062bacafc0c5ed46e31"}

$ curl -sS -X POST http://127.0.0.1:8123/auth/token \
    -d grant_type=authorization_code -d code="$CODE" -d client_id=http://127.0.0.1:8123/
token erneuert, expires_in = 1800
```

Es wurden **keine** HA-Daten verändert (kein Benutzer, kein Entry, kein
Dashboard) — nur der lokale Access-/Refresh-Token. Das Passwort selbst wurde
**nicht** aus dem Token-Store kopiert oder protokolliert.

### A.2 Gegenprobe: Instanz == Repo (kein Cache-Stand auf der Instanz)

```
$ diff -r --brief -x '__pycache__' \
    /home/hermes/repos/ha-health-o-mat/custom_components/health_o_mat \
    /home/hermes/ha-test/config/custom_components/health_o_mat
diff-RC=0
```

**Hash-Gegenprobe (Ende des Laufs):**

```
health-o-mat-card.js          repo=9d420c854de1ba49fdde2c8148e31e4e  instanz=9d420c854de1ba49fdde2c8148e31e4e  OK
health-o-mat-panel-base.js     repo=8fd5b5b444688a4eed3390d2498438fb  instanz=8fd5b5b444688a4eed3390d2498438fb  OK
health-o-mat-panel-views.js    repo=206dba3b41fb4279074f1c40cbed98b9  instanz=206dba3b41fb4279074f1c40cbed98b9  OK
```

**Gegenprobe über HTTP** (was der Browser tatsächlich lädt — die Module tragen
den unveränderten Cache-Buster `?v=0.8.0`):

```
$ curl -sS -H "Authorization: Bearer $ACCESS" \
    "http://127.0.0.1:8123/health_o_mat/health-o-mat-card.js?v=0.8.0" | md5sum
9d420c854de1ba49fdde2c8148e31e4e
$ curl -sS -H "Authorization: Bearer $ACCESS" \
    "http://127.0.0.1:8123/health_o_mat/health-o-mat-panel-base.js?v=0.8.0" | md5sum
8fd5b5b444688a4eed3390d2498438fb
$ curl -sS -H "Authorization: Bearer $ACCESS" \
    "http://127.0.0.1:8123/health_o_mat/health-o-mat-panel-views.js?v=0.8.0" | md5sum
206dba3b41fb4279074f1c40cbed98b9
```

**Im Browser tatsächlich geladene Module** (aus den `response`-Events von
Playwright, mit abgeschaltetem HTTP-Cache — siehe B.1):

```json
{
 "health-o-mat-panel-base.js": {
  "url": "http://127.0.0.1:8123/health_o_mat/health-o-mat-panel-base.js?v=0.8.0",
  "md5": "8fd5b5b444688a4eed3390d2498438fb",
  "bytes": 40792
 },
 "health-o-mat-panel-views.js": {
  "url": "http://127.0.0.1:8123/health_o_mat/health-o-mat-panel-views.js?v=0.8.0",
  "md5": "206dba3b41fb4279074f1c40cbed98b9",
  "bytes": 18438
 },
 "health-o-mat-card.js": {
  "url": "http://127.0.0.1:8123/health_o_mat/health-o-mat-card.js?v=0.8.0",
  "md5": "9d420c854de1ba49fdde2c8148e31e4e",
  "bytes": 40664
 }
}
```

→ Die Belege in diesem Bericht gehören **nachweisbar** zum ausgelieferten Code
(drei unabhängige md5-Quellen: Repo-Datei, HTTP-Auslieferung, Browser-Response).

### A.3 Neustart-Fehlerfreiheit (wörtlicher Logauszug)

```
$ cd /home/hermes/ha-test && docker compose logs --since "2026-10-20T01:26:40" \
    | sed 's/\x1b\[[0-9;]*m//g' | grep -inE "ERROR|WARNING|Traceback|Exception|recorder|unit of"
9:ha-test  | s6-rc: warning: service s6rc-oneshot-runner is marked as essential, not stopping it
19:ha-test  | 2026-10-20 01:26:54.260 WARNING (SyncWorker_0) [homeassistant.loader] We found a custom integration command_gauge which has not been tested by Home Assistant. This component might cause stability problems, be sure to disable it if you experience issues with Home Assistant
20:ha-test  | 2026-10-20 01:26:54.263 WARNING (SyncWorker_0) [homeassistant.loader] We found a custom integration go_gauge which has not been tested by Home Assistant. This component might cause stability problems, be sure to disable it if you experience issues with Home Assistant
21:ha-test  | 2026-10-20 01:26:54.264 WARNING (SyncWorker_0) [homeassistant.loader] We found a custom integration health_o_mat which has not been tested by Home Assistant. This component might cause stability problems, be sure to disable it if you experience issues with Home Assistant
22:ha-test  | 2026-10-20 01:26:57.804 WARNING (MainThread) [custom_components.go_gauge.coordinator] Go Gauge ws1: Abruf fehlgeschlagen (401, message='Unauthorized', url='https://opencode.ai/zen/go/v1/usage') - behalte alten Stand
23:ha-test  | 2026-10-20 01:26:57.804 WARNING (MainThread) [custom_components.go_gauge.coordinator] Go Gauge: kein Workspace mit aktiven Nutzungsdaten (alle no_subscription/error)
```

→ **Keine** Exception, **kein** Traceback, **keine** Recorder-/Statistik-Warnung,
**keine** Meldung aus `health_o_mat` selbst. Die verbleibenden Zeilen sind der
Standard-Hinweis „custom integration … not tested by Home Assistant" (gilt für
alle drei Custom-Integrationen der geteilten Instanz) sowie zwei
herkunftsfremde `go_gauge`-Warnungen (anderes Plugin-Repo).

Eine weitere ERROR-Zeile erscheint um **01:33:59** — sie stammt aus dem
**Löschversuch des temporären Dashboards** mit `bin/lovelace delete`
(Parameter `url_path` ist in dieser HA-Version nicht mehr gültig, siehe G.2) und
ist **nicht** integrationsseitig:

```
24:ha-test  | 2026-10-20 01:33:59.588 ERROR (MainThread) [homeassistant.components.websocket_api.http.connection] [5538752050000] Error handling message: not a valid option at 'url_path'. Got 'hom-e2e-card'
```

**Historische `ml`/`mL`-Warnungen — klar als historisch gekennzeichnet:** Sie
betreffen ausschließlich die **Volumen-Sensoren** (`drinks_today`,
`lifetime_total`), **nicht** die Score-Entity, und stammen aus der Zeit **vor**
dem Sync des Branches mit `mL` (letzter Treffer **2026-10-18 21:15:10**, also
**zwei Tage vor** diesem Lauf):

```
2026-10-18 21:15:10.134 WARNING (Recorder) [homeassistant.components.sensor.recorder] The unit of sensor.health_o_mat_max_drinks_today (mL) cannot be converted to the unit of previously compiled statistics (ml). Generation of long term statistics will be suppressed unless the unit changes back to ml or a compatible unit. Go to https://my.home-assistant.io/redirect/developer_statistics to fix this
2026-10-18 21:15:10.135 WARNING (Recorder) [homeassistant.components.sensor.recorder] The unit of sensor.health_o_mat_e2e_drinks_today (mL) cannot be converted to the unit of previously compiled statistics (ml). …
2026-10-18 21:15:10.135 WARNING (Recorder) [homeassistant.components.sensor.recorder] The unit of sensor.health_o_mat_e2e_lifetime_total (mL) cannot be converted to the unit of previously compiled statistics (ml). …
2026-10-18 21:15:10.135 WARNING (Recorder) [homeassistant.components.sensor.recorder] The unit of sensor.health_o_mat_max_lifetime_total (mL) cannot be converted to the unit of previously compiled statistics (ml). …
```

### A.4 Konfigurations-Entries (nur IDs/Titel, keine Gesundheitsdaten)

```
$ python3 ws_client.py config_entries
01M1SR33KP4E4B43V0KQRE0KTB | Health-O-Mat · Max | loaded
01M1VC3VJ7253D4JAHMJ3DVNT2 | Health-O-Mat · E2E | loaded
```

---

## B) Entity-Verifikation (REST)

### B.1 Score-Entities

| entity_id | state | unit_of_measurement | state_class | device_class | reported_at | scale_max |
|---|---|---|---|---|---|---|
| `sensor.health_o_mat_e2e_wellbeing_score` | `2` | **null (fehlt)** | `measurement` | **fehlt** | `2026-10-20T01:32:24.444619+02:00` | `5` |
| `sensor.health_o_mat_max_wellbeing_score` | `unknown` | **null (fehlt)** | `measurement` | **fehlt** | `null` | `5` |

Wörtliche API-Ausgabe (`GET /api/states/sensor.health_o_mat_e2e_wellbeing_score`,
Session-Ende):

```json
{
  "entity_id": "sensor.health_o_mat_e2e_wellbeing_score",
  "state": "2",
  "attributes": {
    "state_class": "measurement",
    "reported_at": "2026-10-20T01:32:24.444619+02:00",
    "scale_max": 5,
    "icon": "mdi:emoticon-outline",
    "friendly_name": "Health-O-Mat E2E Wohlbefinden-Score"
  },
  "last_changed": "2026-10-19T23:32:24.444619+00:00",
  "last_reported": "2026-10-19T23:32:24.444619+00:00",
  "last_updated": "2026-10-19T23:32:24.444619+00:00"
}
```

Wörtliche API-Ausgabe (`GET /api/states/sensor.health_o_mat_max_wellbeing_score`):

```json
{
  "entity_id": "sensor.health_o_mat_max_wellbeing_score",
  "state": "unknown",
  "attributes": {
    "state_class": "measurement",
    "reported_at": null,
    "scale_max": 5,
    "icon": "mdi:emoticon-outline",
    "friendly_name": "Health-O-Mat Max Wohlbefinden-Score"
  }
}
```

→ **Keine Einheit** (`unit_of_measurement` fehlt komplett), **kein**
`device_class`, `state_class = measurement` ⇒ Regressionsabwehr gegen den
`ml`/`mL`-Recorder-Warnbug ist erfüllt.

### B.2 `unknown`-Beleg ohne Meldung

Person **Max** hat **keine** Wohlbefinden-Meldung:

```
$ GET /api/states/select.health_o_mat_max_wellbeing
state = unknown
$ GET /api/states/sensor.health_o_mat_max_wellbeing_last_reported
state = unknown
$ GET /api/states/sensor.health_o_mat_max_wellbeing_score
state = unknown
```

⇒ Der Leerfall ist **`unknown`** — weder `0` noch `1`. Zusatzbeleg aus der
Recorder-DB: für `sensor.health_o_mat_max_wellbeing_score` existiert **kein**
`statistics_meta`-Eintrag (unbekannte States landen nicht in der Statistik) —
es wird also **kein** 0-Wert in die Statistik geschrieben (siehe C.1).

### B.3 Plausibilität: Score ↔ aktueller Wohlbefinden-Key

| Person | `select.…_wellbeing` | `sensor.…_wellbeing_last_reported` | Score-Entity | erwartet (Index+1) |
|---|---|---|---|---|
| E2E (vor diesem Lauf) | `great` | `2026-10-20T00:53:24+02:00` | `5` | `great` = Index 4 → **5** ✓ |
| E2E (nach Meldung im Panel, D.2) | `bad` | `2026-10-20T01:32:24+02:00` | `2` | `bad` = Index 1 → **2** ✓ |
| Max | `unknown` | `unknown` | `unknown` | keine Meldung → **unknown** ✓ |

### B.4 Keine Änderung an bestehenden Entities (Regressionskontrolle)

Vergleich `/api/states` **vor** dem Sync (2026-10-20 01:24) vs. **nach** der
gesamten Session (2026-10-20 01:48):

```
health_o_mat entities (Session-Ende): 76 | vorher: 76
NEU: []
WEG: []

=== State geaendert ===
  select.health_o_mat_e2e_wellbeing : great -> bad
  sensor.health_o_mat_e2e_wellbeing_last_reported : 2026-10-19T22:53:24+00:00 -> 2026-10-19T23:32:24+00:00
  sensor.health_o_mat_e2e_wellbeing_score : 5 -> 2

=== Attribute geaendert (unit/state_class/device_class) ===
  (keine)
```

⇒ Die **einzigen** Zustandsänderungen sind die **dokumentierte**
Wohlbefinden-Testmeldung (D.2). **76 Entities konstant**, keine Entity
verschwunden, keine umbenannt, keine Einheit geändert.

Bestands-Entities mit **unveränderter** Einheit (Auszug, Session-Ende):

```
  sensor.health_o_mat_e2e_blood_pressure_diastolic: state '84'  | unit 'mmHg'
  sensor.health_o_mat_e2e_blood_pressure_systolic:  state '128' | unit 'mmHg'
  sensor.health_o_mat_e2e_pulse:                      state '66'  | unit 'BPM'
  sensor.health_o_mat_e2e_drinks_today:               state '0'   | unit 'mL'
  sensor.health_o_mat_e2e_lifetime_total:             state '1000'| unit 'mL'
  sensor.health_o_mat_max_blood_pressure_diastolic:  state '84'  | unit 'mmHg'
  sensor.health_o_mat_max_blood_pressure_systolic:   state '128' | unit 'mmHg'
  sensor.health_o_mat_max_pulse:                      state 'unknown' | unit 'BPM'
  sensor.health_o_mat_max_drinks_today:               state '0'   | unit 'mL'
  sensor.health_o_mat_max_lifetime_total:             state '250' | unit 'mL'
```

⇒ `mL` bei den Volumen-Sensoren **unverändert** (Regressionsabwehr N-10/F10).

---

## C) Recorder-/Statistik-Verifikation

### C.1 Keine Einheiten-/Converter-Warnung (wörtlicher Logauszug)

```
$ cd /home/hermes/ha-test && docker compose logs --since "2026-10-20T01:26:40" \
    | sed 's/\x1b\[[0-9;]*m//g' | grep -iE "unit of|previously compiled statistics|recorder|statistics"
(keine Treffer = keine Recorder-/Einheiten-Warnung)

$ cd /home/hermes/ha-test && docker compose logs 2>&1 \
    | sed 's/\x1b\[[0-9;]*m//g' | grep -icE "unit of .*wellbeing_score|wellbeing_score.*unit of"
0

$ cd /home/hermes/ha-test && docker compose logs 2>&1 \
    | sed 's/\x1b\[[0-9;]*m//g' | grep -icE "wellbeing_score"
0
```

→ **NULL** Treffer zur Score-Entity im **gesamten** Log-Archiv — die
Score-Entity kommt im Recorder-Log nicht einmal vor (keine Einheiten- und
keine Converter-Warnung).

### C.2 Recorder-Metadaten der Score-Entity (DB-Zeile, wörtlich)

```
$ docker exec ha-test python3 /tmp/recorder_check.py
=== statistics_meta fuer Score-Entities ===
   id | statistic_id | source | unit_of_measurement | unit_class | has_mean | has_sum | name
  (30, 'sensor.health_o_mat_e2e_wellbeing_score', 'recorder', None, 'unitless', None, 0, None)
```

→ `unit_of_measurement = NULL`, `unit_class = 'unitless'` — der Recorder
akzeptiert die Statistik ohne Einheiten-Konflikt. Für
`sensor.health_o_mat_max_wellbeing_score` (unknown) existiert **keine**
`statistics_meta`-Zeile.

### C.3 Statistik-Zeilen (Kurzzeit + Langzeit, wörtlich)

```
=== statistics_short_term fuer metadata_id=30 (sensor.health_o_mat_e2e_wellbeing_score) ===
   (204131, None, 1792446600.0, 2.0, 2.0, 2.0, None, None)
   (204154, None, 1792446900.0, 3.3886631266666667, 2.0, 4.0, None, None)
   …
   (204499, None, 1792451400.0, 5.0, 5.0, 5.0, None, None)
   (204522, None, 1792451700.0, 5.0, 5.0, 5.0, None, None)
   (204545, None, 1792452000.0, 5.0, 5.0, 5.0, None, None)
=== statistics (Langzeit) fuer metadata_id=30 ===
   (17055, None, 1792443600.0, 2.6943315633333333, 2.0, 4.0, None, None)
   (17078, None, 1792447200.0, 4.00057679, 1.0, 5.0, None, None)
```

→ Sowohl **Kurzzeit-** (`statistics_short_term`) als auch **Langzeit-**
(`statistics`) enthalten Zeilen für die Score-Entity; die Werte liegen im
Skalenbereich 1…5.

---

## D) WS-Beleg (`health_o_mat/panel_data`)

### D.1 Person E2E — aktueller Block + Historie

```
$ python3 ws_client.py panel_data 01M1VC3VJ7253D4JAHMJ3DVNT2
```

Top-Level-Keys (unverändert gegenüber dem Vorlauf):

```
['areas', 'bp', 'entities', 'entry_id', 'goal_ml', 'person', 'person_anchor',
 'person_slug', 'reset_hour', 'today', 'wellbeing']
```

`wellbeing` (aktueller Block, Session-Ende):

```json
{
 "key": "bad",
 "label": "Schlecht",
 "emoji": "🙁",
 "at": "2026-10-20T01:32:24.444619+02:00",
 "score": 2
}
```

`wellbeing.history` (letzte drei Einträge — der letzte ist der **abgelöste**
Status):

```json
[
 {"key": "good",     "label": "Gut",          "emoji": "🙂", "score": 4, "ts": "2026-10-20T00:51:13.551690+02:00"},
 {"key": "very_bad", "label": "Sehr schlecht","emoji": "😵", "score": 1, "ts": "2026-10-20T00:53:24.645381+02:00"},
 {"key": "great",    "label": "Super",        "emoji": "😄", "score": 5, "ts": "2026-10-20T01:32:24.444619+02:00"}
]
```

`entities`-Block (unverändert; **neuer** Key `wellbeing_score`):

```json
{
 "drinks_today": "sensor.health_o_mat_e2e_drinks_today",
 "percent": "sensor.health_o_mat_e2e_daily_goal_progress",
 "lifetime": "sensor.health_o_mat_e2e_lifetime_total",
 "bp_sys": "sensor.health_o_mat_e2e_blood_pressure_systolic",
 "bp_dia": "sensor.health_o_mat_e2e_blood_pressure_diastolic",
 "bp_pulse": "sensor.health_o_mat_e2e_pulse",
 "bp_category": "sensor.health_o_mat_e2e_blood_pressure_category",
 "wellbeing": "sensor.health_o_mat_e2e_wellbeing_last_reported",
 "drinks_history": "sensor.health_o_mat_e2e_drinks_history",
 "bp_history": "sensor.health_o_mat_e2e_blood_pressure_history",
 "drinks_trend": "sensor.health_o_mat_e2e_drinks_trend",
 "bp_trend": "sensor.health_o_mat_e2e_blood_pressure_trend",
 "goal_streak": "sensor.health_o_mat_e2e_goal_streak",
 "caffeine_today": "sensor.health_o_mat_e2e_caffeine_today",
 "wellbeing_score": "sensor.health_o_mat_e2e_wellbeing_score"
}
```

→ Der aktuelle Score (`2`) und der **letzte Historieneintrag** (`5`) sind
**verschieden** — genau der Kontrast, den der Chart korrekt abbilden muss.

### D.2 Person Max — Leerfall

```json
{
 "key": null,
 "label": null,
 "emoji": null,
 "at": null,
 "score": null,
 "history": []
}
```

---

## E) Chart-Verifikation (Panel)

### E.1 Setup: Historie ≠ aktueller Wert

Die **Session-Startlage** der Person E2E erfüllte die Bedingung bereits:

| Zeitpunkt | Quelle | Key | Score | Wirkung |
|---|---|---|---|---|
| 2026-10-20 00:53:24 +02:00 | Vorlauf (Panel-Klick) | `great` | 5 | aktueller Wert **vor** diesem Lauf; letzter Historieneintrag `very_bad` (1) |
| **2026-10-20 01:32:24 +02:00** | **dieser Lauf** (Panel-Klick auf „Schlecht") | `bad` | **2** | aktueller Wert; letzter Historieneintrag wird `great` (5) |

Zusätzlich wurde im Vorlauf am 2026-10-20 00:51:13 +02:00 über
`select.select_option` (Meldung **außerhalb** des Panels) `very_bad` gesetzt —
die Historie enthält deshalb neun Einträge mit **unterschiedlichen Keys**.

### E.2 Browser-Setup (Cache umgehen)

Die JS-Module tragen den **unveränderten** Cache-Buster `?v=0.8.0` — ein
Browser-Cache könnte therefore einen **alten** Stand liefern. Deshalb:

* **frischer Browser-Kontext** (`browser.new_context()`, kein persistentes
  Profil, leerer HTTP-Cache),
* **Cache im CDP abgeschaltet**:
  `cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})`,
* zusätzliche Request-Header `Cache-Control: no-cache` / `Pragma: no-cache`.

Gegenprobe: die im Browser geladenen Module haben exakt die md5-Summen des
Repos (A.2) ⇒ es wurde der **finale** Stand gerendert.

### E.3 Panel — Normalfall (Person E2E, Desktop 1600×900)

**Kopfzeile (wörtlicher DOM-Auszug, `.tile-row`):**

```html
<div class="tile-row">
      <span class="em" aria-hidden="true">😄</span>
      <span>Zuletzt: <strong>Super</strong> · 5 / 5</span>
      <span class="muted">· vor 39 min</span>
    </div>
```

als Text: `😄 Zuletzt: Super · 5 / 5 · vor 39 min`

**`aria-label` des Chart-SVGs (wörtlich):**

```
Wohlbefinden-Score-Verlauf: 9 Meldungen, aktuell 5 von 5 (Super)
```

(64 Zeichen — Browser-Textauszüge sind **Zeichen**, keine Bytes.)

**`point-current`-Kreis mit `<title>` (wörtlich):**

```
cx="306.0" cy="14.0" r="5"
<title>20.10.2026, 00:53 Uhr – Super (5 / 5)</title>
```

**Letzter Historienpunkt (wörtlich):**

```
cx="306.0" cy="154.0" r="3.2"
<title>20.10.2026, 00:53 Uhr – Sehr schlecht (1 / 5)</title>
```

**Weitere Chart-Belege (wörtlich):**

```
role="img"   viewBox="0 0 320 180"
Punkte gesamt: 9 | point-current: 1 | <title>-Elemente: 9 | Gridlines: 5
Y-Achsenbeschriftungen: ['1', '2', '3', '4', '5', '06.09.', '20.10.']
Achsen-Extremwerte: ['1', '5']
SVG wohlgeformt (DOMParser, kein parsererror): True
NaN/undefined/Infinity im Chart-HTML: False
Hinweis: 1 = Sehr schlecht · 5 = Super
```

> **Kernbeleg:** Kopfzeile (`5 / 5`), `aria-label` (`aktuell 5 von 5`) und
> `point-current` (`(5 / 5)`) nennen **denselben, aktuellen** Score 5. Der
> letzte Historienpunkt nennt **1 / 5** (Sehr schlecht) — er **weicht
> ab** (und wird **nicht** markiert: `r="3.2"` statt `r="5"`, Klasse `point`
> statt `point point-current`). Das ist der behobene Bug, explizit belegt.

**Screenshot:** `panel-wellbeing-score-desktop.png` (1600×900) — manuell
sichtprüfbar: der gefüllte Marker sitzt **oben rechts** (Score 5), der
letzte Historienpunkt **unten rechts** (Score 1).

### E.4 Panel — Live-Update ohne Reload (2026-10-20 01:32:24 +02:00)

Klick auf den Panel-Button „Schlecht" (`data-action="wb"`, `data-key="bad"`) —
**ohne** Reload:

| | vorher | nachher |
|---|---|---|
| `aria-label` | `Wohlbefinden-Score-Verlauf: 9 Meldungen, aktuell 5 von 5 (Super)` | `Wohlbefinden-Score-Verlauf: 10 Meldungen, aktuell 2 von 5 (Schlecht)` |
| Kopfzeile | `😄 Zuletzt: Super · 5 / 5 · vor 39 min` | `🙁 Zuletzt: Schlecht · 2 / 5 · gerade eben` |
| `point-current`-Tooltip | `20.10.2026, 00:53 Uhr – Super (5 / 5)` | `20.10.2026, 01:32 Uhr – Schlecht (2 / 5)` |
| letzter Historienpunkt | `20.10.2026, 00:53 Uhr – Sehr schlecht (1 / 5)` | `20.10.2026, 01:32 Uhr – Super (5 / 5)` |
| `point-current`-Anzahl | 1 | 1 |

→ Der Marker **folgt** dem neuen Wert ohne Reload; der abgelöste Wert
(„Super", 5) rutscht in die Historie und ist **nicht** markiert.

**Screenshot:** `panel-wellbeing-score-inpanel-update.png`.

### E.5 Panel — Leerfall (Person Max, ohne Meldung)

```
svg_present: False
empty_messages: ['Noch keine Wohlbefinden-Meldung – der Verlauf erscheint nach der ersten Meldung.']
Kopfzeile: 🙂 Zuletzt: Keine Angabe
```

→ Verständlicher Hinweis statt eines leeren/kaputten SVG.

**Screenshot:** `panel-wellbeing-score-empty.png`.

### E.6 Panel — Mobil (390×844)

**Screenshot:** `panel-wellbeing-score-mobile.png` — der Marker sitzt oben
rechts (5), der letzte Historienpunkt unten rechts (1); die Y-Achse 1…5 ist
lesbar.

### E.7 Panel — Datenschutz-Scan (keine Blutdruckwerte im Wohlbefinden-Tab)

Der **sichtbare Text des Tab-Inhalts** (ohne die Tab-Leiste, die nur
Navigations-Labels wie „Blutdruck" enthält) wurde gegen folgende Muster
geprüft: `\d{2,3}\s*/\s*\d{2,3}`, `\b\d{2,3}\s*bpm\b`, `mmHg`, `\bbpm\b`,
`Blutdruck`, `Puls`, `Systolisch`, `Diastolisch`.

```
Person E2E:  pattern_hits = {}
Person Max:  pattern_hits = {}
```

Auszug des gescannten Inhalts (Person E2E, gekürzt):

```
← | 💧 | Health-O-Mat | ⚙️ | ↻ | E2E | Wie geht es dir? | 😵 | Sehr schlecht | 🙁 |
Schlecht | 😐 | Okay | 🙂 | Gut | 😄 | Super | 🙁 | Zuletzt: | Schlecht | · 2 / 5 | ·
vor 3 min | Score-Verlauf | 1 | 2 | 3 | 4 | 5 | 06.09.2026, 14:47 Uhr – Sehr
schlecht (1 / 5) | … | 20.10.2026, 01:32 Uhr – Super (5 / 5) | 20.10.2026,
01:32 Uhr – Schlecht (2 / 5) | 06.09. | 20.10. | 1 = Sehr schlecht · 5 = Super
| Verlauf | 😵 | vor 43 d | … | Health-O-Mat · keine medizinische Beratung
```

→ **Kein** Blutdruck- und **kein** Pulswert im Wohlbefinden-Tab. (Die
Panel-Screenshots sind damit ebenfalls datenschutzkonform.)

---

## F) Card-Verifikation (echte Lovelace-Card)

### F.1 Ausgangslage

`custom:health-o-mat-card` ist als Lovelace-Ressource registriert:

```json
{
 "id": "34df11e8d25a42b4a017710f00d05f8e",
 "url": "/health_o_mat/health-o-mat-card.js?v=0.8.0",
 "type": "module"
}
```

Die vorhandenen Dashboards (`hom-standard`, `hom-mushroom`, `map`) enthalten
**keine** `custom:health-o-mat-card`-Karte → für die Verifikation wurde ein
**temporäres** Dashboard angelegt (G.2).

### F.2 Card — DOM-Belege (wörtlich)

```
Badge-Text (Wohlbefinden-Zeile):  '2 / 5'
Label / Sub / Emoji:               'Schlecht' | 'Zuletzt vor 8 min' | '🙁'
aria-label (Sparkline):            Wohlbefinden-Trend: 10 Meldungen, aktuell 2 von 5 (Schlecht)
role="img"  viewBox="0 0 320 40"
Punkte gesamt: 10 | point-current: 1 | <title>-Elemente: 10 | Linie: ja
NaN/undefined/Infinity: False

point-current:  cy="27.5"  <title>20.10.2026, 01:32 Uhr – Schlecht (2 / 5)</title>
letzter Historienpunkt: cy="5.0" <title>20.10.2026, 01:32 Uhr – Super (5 / 5)</title>
```

> **Kernbeleg:** Badge (`2 / 5`), `aria-label` (`aktuell 2 von 5`) und
> `point-current` (`(2 / 5)`) zeigen **denselben** Wert; der letzte
> Historienpunkt (5) weicht ab und ist **nicht** markiert.

### F.3 Card — Datenschutz: Screenshot ist auf den Wohlbefinden-Block **zugeschnitten**

Die **vollen** Card-Entities enthalten die Seed-Blutdruckwerte
(`128/84`, `66 bpm`) — der unzugeschnittene Card-Screenshot wäre damit für ein
**öffentliches** Repo nicht akzeptabel. Der abgelegte Screenshot ist deshalb
**ausschließlich** der Wohlbefinden-Block (Badge + Sparkline).

**Ausgeschnittener Bereich (Seitenkoordinaten im Browser):**

```
{'x': 339, 'y': 340, 'width': 478, 'height': 161}
```

**Objektiver Nachweis — alle Elemente, die im Clip-Rechteck liegen
(wörtliche Liste, inkl. Tooltip-Texten):**

```
SPAN  .emoji                     '🙁'
DIV   .big                       'Schlecht'
DIV   .sub                       'Zuletzt vor 8 min'
SPAN  .score                     '2 / 5'
circle>title .point              '06.09.2026, 14:47 Uhr – Sehr schlecht (1 / 5)'
circle>title .point              '06.09.2026, 14:47 Uhr – Schlecht (2 / 5)'
circle>title .point              '06.09.2026, 14:47 Uhr – Okay (3 / 5)'
circle>title .point              '06.09.2026, 14:47 Uhr – Gut (4 / 5)'
circle>title .point              '06.09.2026, 14:47 Uhr – Super (5 / 5)'
circle>title .point              '19.10.2026, 23:56 Uhr – Schlecht (2 / 5)'
circle>title .point              '20.10.2026, 00:51 Uhr – Gut (4 / 5)'
circle>title .point              '20.10.2026, 00:53 Uhr – Sehr schlecht (1 / 5)'
circle>title .point              '20.10.2026, 01:32 Uhr – Super (5 / 5)'
circle>title .point point-current '20.10.2026, 01:32 Uhr – Schlecht (2 / 5)'
```

**Muster-Scan des ausgeschnittenen Bereichs:**

```
forbidden_in_clip     = []            # 128/84, 66 bpm, mmHg, bpm, Puls, Blutdruck …
forbidden_in_full_card = ['128/84', '66 bpm', 'bpm']
```

⇒ Der ausgelieferte Screenshot enthält **keine** Blutdruck-/Pulswerte; die
gesamte Card hätte sie enthalten (der Unterschied belegt, dass der Crop
greift). Sichtprüfung des PNG bestätigt: nur Emoji, „Schlecht",
„Zuletzt vor 8 min", Badge „2 / 5" und die Sparkline.

**Screenshot:** `card-wellbeing-score.png` (478×161 px, **zugeschnitten**).
**Sparkline-SVG (roh):** `card-wellbeing-score-trend.svg`.

### F.4 Card — Leerfall

`_wellbeing()` rendert ohne Meldung und ohne Historie:

```html
<div class="row">
  <span class="emoji" aria-hidden="true">🙂</span>
  <div class="label">
    <div class="big">Keine Angabe</div>
    <div class="sub">Noch keine Wohlbefinden-Meldung</div>
  </div>
</div>
```

→ Verständlicher Hinweis, **kein** leeres/kaputtes SVG (kein `point-current`,
kein Badge).

---

## G) Aufräumen (restlos)

### G.1 Option `enable_sidebar_panel` (temporär, restauriert)

Das Sidebar-Panel ist per Default **aus**; für die Panel-Screenshots wurde die
Option der Person E2E über den **echten Options-Flow** der Integration
temporär `false → true` gesetzt und danach **auf den Ausgangswert `false`
zurückgesetzt** (alle übrigen Optionen unverändert):

```
OPTIONS VORHER: {… "enable_sidebar_panel": false …}
OPTIONS NACHHER (Wiederherstellung): {… "enable_sidebar_panel": false …}
DIFF: {}
```

Endzustand der Optionen der Person E2E:

```json
{"areas": {"bp": true, "drink": true, "wellbeing": true}, "daily_goal_ml": 800,
 "daily_reset_hour": 0, "drink_lexicon": {"beer": ["Bier", 500], "kaffee": ["Kaffee", 250]},
 "enable_sidebar_panel": false, "person_display": "E2E",
 "quick_drinks": [{"icon": "mdi:glass-water", "key": "slot_0", "label": "Glas Wasser", "ml": 200},
                  {"icon": "mdi:bottle-water", "key": "slot_1", "label": "Flasche Wasser", "ml": 500},
                  {"icon": "mdi:coffee", "key": "slot_2", "label": "Tasse Kaffee", "ml": 250},
                  {"icon": "mdi:fruit-citrus", "key": "slot_3", "label": "Glas Saft", "ml": 200}],
 "retention_months": 0, "set_lifetime_ml": 1000}
```

```
$ curl -s -o /dev/null -w "GET /health-o-mat -> HTTP=%{http_code}\n" http://127.0.0.1:8123/health-o-mat
GET /health-o-mat -> HTTP=404
```

⇒ Panel wieder abgemeldet (Ausgangszustand).

### G.2 Temporäres Lovelace-Dashboard `hom-e2e-card` (wieder entfernt)

```
storage_files_before   = ['lovelace.hom_mushroom', 'lovelace.hom_standard', 'lovelace.map', 'lovelace_dashboards', 'lovelace_resources']
storage_files_with     = ['lovelace.hom_e2e_card', 'lovelace.hom_mushroom', 'lovelace.hom_standard', 'lovelace.map', 'lovelace_dashboards', 'lovelace_resources']
storage_files_after    = ['lovelace.hom_mushroom', 'lovelace.hom_standard', 'lovelace.map', 'lovelace_dashboards', 'lovelace_resources']
cleanup = {"id": 1, "type": "result", "success": true, "result": null}
```

```
$ md5sum config/.storage/lovelace_dashboards /tmp/hom-e2e/lovelace_dashboards.BACKUP.json
11c905f21ccbdd3c71dbef637e40f338  config/.storage/lovelace_dashboards
11c905f21ccbdd3c71dbef637e40f338  /tmp/hom-e2e/lovelace_dashboards.BACKUP.json
$ diff config/.storage/lovelace_dashboards /tmp/hom-e2e/lovelace_dashboards.BACKUP.json
(identisch)

$ curl -s -o /dev/null -w "GET /hom-e2e-card -> HTTP=%{http_code}\n" http://127.0.0.1:8123/hom-e2e-card
GET /hom-e2e-card -> HTTP=404
```

⇒ `lovelace_dashboards` ist **md5-identisch** mit dem Backup vor dem Anlegen;
das temporäre Dashboard ist restlos entfernt.

> **Hinweis:** `bin/lovelace delete hom-e2e-card` schlug in dieser HA-Version
> fehl (`not a valid option at 'url_path'` — verlangt wird `dashboard_id`).
> Das Löschen erfolgte deshalb über denselben WebSocket-Endpunkt mit
> `dashboard_id="hom_e2e_card"` (Ergebnis oben). Der verbleibende
> ERROR-Logeintrag (01:33:59) stammt aus dem fehlgeschlagenen
> `bin/lovelace`-Versuch, nicht aus der Integration.

---

## H) Regressionstests (neu, `tests/test_panel_js.py`)

### H.1 Neue Testfälle

| Datei :: Testname | Zweck |
|---|---|
| `tests/test_panel_js.py :: test_req_hom_112_panel_chart_marks_exactly_one_current_point` | Normalfall: genau **ein** `point-current`, `aria-label` „aktuell N von M", Marker-Score == aktueller Score; der letzte Historienpunkt ist **nicht** markiert |
| `tests/test_panel_js.py :: test_req_hom_112_panel_chart_without_current_score_marks_nothing` | Restfall: `current = {score: null, key: "good"}` ⇒ **kein** `point-current`; `aria-label` enthält „letzter Wert" und **nicht** „aktuell" |
| `tests/test_panel_js.py :: test_req_hom_112_card_without_current_score_has_no_badge_and_no_current_point` | Card analog: **kein** Score-Badge, **kein** `point-current`, Sparkline behauptet keinen aktuellen Wert (Kontrollfall: die Historie ist gerendert) |
| `tests/test_panel_js.py :: test_req_hom_112_card_with_current_score_shows_badge_and_one_current_point` | Card-Normalfall: Badge und Marker zeigen denselben Wert |
| `tests/test_panel_js.py :: test_req_hom_112_panel_prefers_live_label_and_emoji_over_stale_snapshot` | Live-first: Live-Attribute `label`/`emoji` schlagen den veralteten Snapshot (Kopfzeile **und** `aria-label`) |
| `tests/test_panel_js.py :: test_req_hom_112_panel_falls_back_to_snapshot_label_and_emoji` | Ohne Live-Attribute fällt der Panel-Text auf den Snapshot zurück |
| `tests/test_panel_js.py :: test_req_hom_112_card_prefers_live_label_and_emoji_over_stale_snapshot` | Live-first in der Card |
| `tests/test_panel_js.py :: test_req_hom_112_card_falls_back_to_snapshot_label_and_emoji` | Fallback in der Card |
| `tests/test_panel_js.py :: test_req_hom_112_panel_base_wellbeing_score_follows_server_truth_rule[null-key]` | Ergänzung der JS-Regeltabelle: `key: null` ⇒ **kein** Score |
| `tests/test_panel_js.py :: test_req_hom_112_panel_base_wellbeing_score_follows_server_truth_rule[empty-key]` | `key: ""` ⇒ **kein** Score |
| `tests/test_panel_js.py :: test_req_hom_112_panel_base_wellbeing_score_follows_server_truth_rule[non-string-key]` | `key: 123` ⇒ **kein** Score |
| `tests/test_panel_js.py :: test_req_hom_112_card_wellbeing_score_follows_server_truth_rule[null-key\|empty-key\|non-string-key]` | dieselben drei Randfälle in der Card |

> **Wichtig:** Der Restfall-Test hängt **nicht** davon ab, dass `current`
> fehlt — `current` ist **vorhanden** (`{score: null, key: "good"}`), nur ohne
> verwertbaren Score.

### H.2 Testlauf (wörtlich)

```
$ cd /home/hermes/repos/ha-health-o-mat && pytest -q
666 passed, 1 warning in 5.47s
```

Vorher: **652 passed** ⇒ **+14 Tests** (8 neue Testfunktionen + 6 neue
Parametrisierungsfälle in der JS-Regeltabelle).

```
$ ruff check .
All checks passed!
$ ruff format --check .
46 files already formatted
```

### H.3 Mutationsprobe (Pflicht)

**Baseline (sha256 der finalen JS-Dateien):**

```
fbdce3bbbb2f175451fc77abd31547c2da7eee08291c95cedea50502d648281d  health-o-mat-card.js
8bca7da6e39f91c91d1346a2fb4d756207d8e7f8d60d961222241ca50569c0f0  health-o-mat-panel-base.js
d8f4ded28c715e6d574dffa247ffe505be18853b1fba90430289a3b836a62810  health-o-mat-panel-views.js
```

**Mutation (a) — `panel-base.js`: `isCurrent`-Bedingung ausgehebelt**

```diff
-    const current = point.isCurrent === true;
+    const current = index === list.length - 1;
```

Ergebnis:

```
FAILED tests/test_panel_js.py::test_req_hom_112_panel_chart_without_current_score_marks_nothing
E       AssertionError: ohne aktuellen Wert darf kein Punkt hervorgehoben werden:
E         [{'cls': 'point point-current', 'score': '2',
E           'title': '19.10.2026, 18:00 Uhr – Wohlbefinden (2 / 5)'}]
1 failed, 52 passed, 1 warning in 3.13s
```

**Mutation (b) — `card.js`: derselbe Fall**

```diff
-    const current = point.isCurrent === true;
+    const current = index === list.length - 1;
```

Ergebnis:

```
FAILED tests/test_panel_js.py::test_req_hom_112_card_without_current_score_has_no_badge_and_no_current_point
E       AssertionError: ohne aktuellen Wert darf die Sparkline keinen Punkt hervorheben:
E         [{'cls': 'point point-current', 'score': None,
E           'title': '19.10.2026, 18:00 Uhr – Wohlbefinden (2 / 5)'}]
1 failed, 52 passed, 1 warning in 3.12s
```

⇒ **Beide Mutationen werden von den neuen Tests gefangen.**

**Rücksetzung — byte-identisch (Beleg gegen die Baseline):**

```
$ sha256sum -c /tmp/hom-e2e/js_baseline.sha256
health-o-mat-card.js: OK
health-o-mat-panel-base.js: OK
health-o-mat-panel-views.js: OK
```

Zustand danach (grün, Produktivcode unverändert):

```
$ pytest -q
666 passed, 1 warning in 5.49s
$ ruff check . && ruff format --check .
All checks passed!
46 files already formatted
```

---

## I) Datenschutz-Hinweis

* **Alle Werte in diesem Bericht stammen aus der synthetischen Testinstanz
  `ha-test`** (Seed-Daten der geteilten HA-Instanz, Testpersonen **„E2E"** und
  **„Max"**). Es sind **keine realen Gesundheitsdaten** — die Blutdruck-/
  Pulswerte der Seed-Entities (`128/84 mmHg`, `66 bpm`) sind Testdaten der
  Testinstanz.
* Der **Card-Screenshot** ist bewusst **auf den Wohlbefinden-Block
  zugeschnitten** (Badge + Sparkline, 478×161 px) und enthält **keine**
  Blutdruck-/Pulswerte (Nachweis in F.3).
* Die **Panel-Screenshots** zeigen ausschließlich den Tab „Wohlbefinden" — ein
  Textscan des Tab-Inhalts belegt **keine** Blutdruck-/Pulswerte (E.7).
* **Nicht committet** werden (bewusst via `.gitignore`):
  * `docker/` — die lokale HA-Laufzeitumgebung inkl. **Auth-Store**,
  * `artifacts/` — die Scratch-Kopie der Belegdateien (untracked, gitignored).
  Beide Verzeichnisse enthalten sensible Testumgebungs-Daten und gehören
  **nicht** ins öffentliche Repository.
* Es wurden **keine** Tokens kopiert, committet oder in diesen Bericht
  aufgenommen; die `.ha-state/token.json` der Testinstanz bleibt lokal
  (`chmod 600`).

---

## J) Offene Punkte / Hinweise

1. **Cache-Buster unverändert (`?v=0.8.0`)** — die JS-Module wurden in diesem
   Feature ohne Versionsanhebung geändert. Für Nutzer mit warmem Browser-Cache
   kann der alte Stand sichtbar bleiben, bis der Cache-Buster nachgezogen wird
   (bewusste Folge des Release-Dreiklangs: `manifest.version` ↔ Tag). **Vor dem
   Release muss die Version angehoben werden**, sonst liefert HACS weiter
   `0.8.0` aus.
2. **Zwei Punkte mit identischem Zeitstempel** — der letzte Historieneintrag
   trägt per Store-Semantik (`store.set_wellbeing`) den Zeitstempel der
   **neuen** Meldung; der angehängte aktuelle Punkt hat denselben Zeitstempel.
   Im Panel-Chart (zeitbasiert) stehen beide deshalb **vertikal übereinander**
   am rechten Rand (im Screenshot sichtbar: Marker oben, abgelöster Punkt
   unten). Das ist die dokumentierte Semantik, kein Renderfehler.
3. **`bin/lovelace delete` ist in HA 2026.9.1 mit `url_path` defekt** — der
   Endpunkt verlangt `dashboard_id` (siehe G.2). Das betrifft die
   **Testinstanz** (`ha-test`), nicht das Repository.
4. **Panel-Registrierung ist Option-Opt-in** — `enable_sidebar_panel` ist per
   Default **aus**; das Panel ist ohne diese Option nicht erreichbar
   (`GET /health-o-mat → HTTP 404`). Für die Panel-Verifikation wurde die
   Option temporär gesetzt und restauriert (G.1).
5. **Kein E2E gegen die HACS-Installation** — dieser Lauf prüft den
   Working-Tree-Stand auf der geteilten Instanz. Der HACS-Update-Test
   (Update von der Vorgängerversion) gehört **nach** dem Release-Dreiklang
   (Workflow-Schritt 7) und ist **nicht** Teil dieses Laufs.

---

## K) Artefakte (frisch erzeugt)

| Datei | Inhalt | Größe |
|---|---|---|
| `E2E-REPORT-REQ-HOM-112.md` | dieser Report | — |
| `panel-wellbeing-score-desktop.png` | Panel, Tab „Wohlbefinden", Desktop 1600×900 | 91 541 B |
| `panel-wellbeing-score-mobile.png` | Panel, Tab „Wohlbefinden", Mobil 390×844 | 41 570 B |
| `panel-wellbeing-score-inpanel-update.png` | Panel nach Live-Meldung (Marker folgt ohne Reload) | 92 637 B |
| `panel-wellbeing-score-empty.png` | Panel, Person ohne Meldung (Hinweis statt Chart) | 56 089 B |
| `panel-wellbeing-score.svg` | gerendertes Chart-SVG (Panel, roh) | 2 368 B |
| `card-wellbeing-score.png` | Card, **auf den Wohlbefinden-Block zugeschnitten** | 10 289 B |
| `card-wellbeing-score-trend.svg` | gerendertes Sparkline-SVG (Card, roh) | 1 465 B |

Dieselben Dateien liegen (frisch überschrieben) in `artifacts/` — dort mit
Unterstrich-Namen (`panel_wellbeing_score_desktop.png` usw.).

**Hilfsskripte des Laufs** (außerhalb des Repos, in `/tmp/hom-e2e/`):
`verify_panel_final.py`, `verify_card_lovelace_final.py`, `verify_bp_scan.py`,
`ws_client.py`, `toggle_panel_option.py`, `recorder_check.py` (im Container),
`panel_dom_final.json`, `card_lovelace_final.json`, `js_baseline.sha256`.

#!/usr/bin/env bash
# Tiefen-Live-Test für health_o_mat auf der geteilten Testinstanz.
# Aufruf:  scripts/e2e-live-test.sh [flags]     (läuft im Repo-Root)
# Flags:   --migration   v0.4.0-Worktree aufsetzen, Alt-Entry anlegen, Update testen
#          --corrupt     Store korrumpieren → Recovery testen (Backup/Restore inkl.)
#          --no-cleanup  Test-Entries danach NICHT löschen (zum Nachsehen)
#          --person NAME Basisname der Testperson (Default: E2E)
#
# Bedient NUR Domains health_o_mat-Einträge der Testpersonen; Fremd-Daten
# (andere Integrationen/Testpersonen) bleiben unberührt. Nur der Corrupt-Test
# fasst den health_o_mat-Store an (mit Backup/Restore),
# Migrations- und Corrupt-Phasen starten HA neu (geteilte Instanz → Etikette beachten).
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"
export HA_TEST="${HA_TEST:-/home/hermes/ha-test}"
PERSON="E2E"
WITH_MIGRATION=0; WITH_CORRUPT=0; CLEANUP=1
for a in "$@"; do
  case "$a" in
    --migration) WITH_MIGRATION=1 ;;
    --corrupt)   WITH_CORRUPT=1 ;;
    --no-cleanup) CLEANUP=0 ;;
    --person) shift; PERSON="$1"; shift ;;
    --person=*) PERSON="${a#--person=}" ;;
    *) echo "unbekannte Option: $a" >&2; exit 1 ;;
  esac
done
export PATH="$HA_TEST/bin:$PATH"
SLUG=$(echo "$PERSON" | tr '[:upper:]' '[:lower:]' | tr ' ' '_' | tr -cd 'a-z0-9_-')
P="health_o_mat_${SLUG}"
OK=0; FAIL=0

step()  { echo; echo "== $* =="; }
pass()  { OK=$((OK+1)); echo "  PASS $1"; }
fail()  { FAIL=$((FAIL+1)); echo "  FAIL $1"; }

state()  { "$HA_TEST/bin/ha" GET "/api/states/$1" 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)['state'])"; }
attr()   { "$HA_TEST/bin/ha" GET "/api/states/$1" 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)['attributes'].get('$2',''))"; }
expect_eq()  { [ "$2" = "$3" ] && pass "$1" || { fail "$1 (erwartet '$3', ist '$2')"; }; }
expect_ne()  { [ "$2" != "$3" ] && pass "$1" || { fail "$1 (unerwartet '$3')"; }; }
expect_json(){ "$HA_TEST/bin/ha" GET "/api/states/$2" 2>/dev/null | python3 -c "import json,sys;json.loads(json.load(sys.stdin)['attributes']['$3'])" >/dev/null 2>&1 && pass "$1" || fail "$1 (kein valides JSON in $3 von $2)"; }
expect_state_unchanged() { # expect_state_unchanged name entity vorher
  [ "$(state "$2")" = "$3" ] && pass "$1 (Zustand unverändert: $3)" \
    || fail "$1 (Zustand änderte sich: $3 → $(state "$2"))";
}
# HA-REST gibt Fehler als reinen "500 Internal Server Error"-Text zurück
# (Meldungstext nicht im Body) → Fehlerpfad = HTTP 500 + unveränderter Zustand
expect_http500() { # expect_http500 name response
  echo "$2" | grep -q "500 Internal Server Error" && pass "$1 (HTTP 500)" \
    || { fail "$1 (kein HTTP 500 in: $(echo "$2" | head -c 160))"; };
}

create_person() {
  local name="$1"
  local flow flow_id
  flow=$("$HA_TEST/bin/ha" POST /api/config/config_entries/flow '{"handler": "health_o_mat"}')
  flow_id=$(echo "$flow" | python3 -c "import json,sys;print(json.load(sys.stdin)['flow_id'])")
  "$HA_TEST/bin/ha" POST "/api/config/config_entries/flow/$flow_id" "{\"person\": \"$name\"}" \
    | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['entry_id'])"
}
delete_entry() { "$HA_TEST/bin/ha" DELETE "/api/config/config_entries/entry/$1" >/dev/null 2>&1 || true; }
# Entry-ID einer Person aus dem Storage lesen (leer wenn nicht vorhanden)
entry_id_for_person() {
  docker exec -i ha-test python3 - "$1" <<'EOF'
import json, sys
name = sys.argv[1]
d = json.load(open('/config/.storage/core.config_entries'))
for e in d['data']['entries']:
    if e['domain'] == 'health_o_mat' and (e.get('data') or {}).get('person') == name:
        print(e['entry_id'])
        break
EOF
}
# Sauberer Start: ggf. liegengebliebene Test-Entries aus abgebrochenen Läufen löschen
ensure_fresh_person() {
  local old
  old=$(entry_id_for_person "$1")
  [ -n "$old" ] && { delete_entry "$old"; echo "  stale entry entfernt: $1"; sleep 2; }
  create_person "$1"
}

# ------------------------------------------------------------------ Preflight
step "Preflight"
ready=""
for i in $(seq 1 30); do
  "$HA_TEST/bin/ha" GET /api/ 2>/dev/null | grep -q "API running" && { ready=1; break; }
  sleep 2
done
[ -n "$ready" ] && pass "API erreichbar" || fail "API erreichbar"
echo "  Sprache: $("$HA_TEST/bin/ha" GET /api/config | python3 -c "import json,sys;print(json.load(sys.stdin)['language'])")"

# ------------------------------------------------------------------ Sync + Setup
step "Sync Plugin + Testperson '$PERSON' anlegen"
"$HA_TEST/bin/sync" "$REPO" >/dev/null 2>&1
sleep 3
ENTRY_ID=$(ensure_fresh_person "$PERSON")
echo "  entry: $ENTRY_ID"

# Erwarteter Entity-Satz (Suffixe aus dem englischen Anzeigenamen)
for e in \
  "sensor:${P}_drinks_today" "sensor:${P}_daily_goal_progress" \
  "sensor:${P}_drinks_history" "sensor:${P}_lifetime_total" \
  "sensor:${P}_blood_pressure_systolic" "sensor:${P}_blood_pressure_diastolic" \
  "sensor:${P}_pulse" "sensor:${P}_blood_pressure_history" \
  "sensor:${P}_wellbeing_last_reported" \
  "binary_sensor:${P}_daily_goal_reached" "binary_sensor:${P}_blood_pressure_warning" \
  "button:${P}_book_custom_amount" "button:${P}_undo_last_drink" \
  "button:${P}_save_measurement" \
  "button:${P}_report_very_bad" "button:${P}_report_bad" "button:${P}_report_okay" \
  "button:${P}_report_good" "button:${P}_report_great" \
  "select:${P}_wellbeing" "text:${P}_log_drink_free_text" \
  "number:${P}_daily_goal" "number:${P}_custom_drink_amount" \
  "number:${P}_systolic_warning_threshold" "number:${P}_diastolic_warning_threshold" \
  "number:${P}_new_reading_systolic" "number:${P}_new_reading_diastolic" \
  "number:${P}_new_reading_pulse"; do
  plat="${e%%:*}"; eid="${e#*:}"
  if "$HA_TEST/bin/ha" GET "/api/states/$eid" >/dev/null 2>&1; then pass "registriert: $eid"; else fail "registriert: $eid"; fi
done

# Quick-Drinks aus Default-Konfiguration
for e in "button:${P}_glas_wasser" "button:${P}_flasche_wasser" "button:${P}_tasse_kaffee" "button:${P}_glas_saft"; do
  eid="${e#*:}"
  "$HA_TEST/bin/ha" GET "/api/states/$eid" >/dev/null 2>&1 && pass "quick: $eid" || fail "quick: $eid"
done

# ------------------------------------------------------------------ Getränke
step "Getränke-Batterie"
v0=$(state "sensor.${P}_drinks_today")
"$HA_TEST/bin/ha" POST /api/services/button/press "{\"entity_id\": \"button.${P}_glas_wasser\"}" >/dev/null
sleep 1
expect_eq "quick-drink +200ml" "$(state "sensor.${P}_drinks_today")" "$(( ${v0%.*} + 200 ))"
"$HA_TEST/bin/ha" POST /api/services/number/set_value "{\"entity_id\": \"number.${P}_custom_drink_amount\", \"value\": 333}" >/dev/null
"$HA_TEST/bin/ha" POST /api/services/button/press "{\"entity_id\": \"button.${P}_book_custom_amount\"}" >/dev/null
sleep 1
expect_eq "custom 333ml" "$(state "sensor.${P}_drinks_today")" "$(( ${v0%.*} + 533 ))"
"$HA_TEST/bin/ha" POST /api/services/text/set_value "{\"entity_id\": \"text.${P}_log_drink_free_text\", \"value\": \"Kaffee 300ml\"}" >/dev/null
sleep 1
expect_eq "freitext kaffee 300" "$(state "sensor.${P}_drinks_today")" "$(( ${v0%.*} + 833 ))"
expect_json "breakdown-Attribut JSON" "sensor.${P}_drinks_today" "breakdown_by_type"
expect_ne "last_drink_at gesetzt" "$(attr "sensor.${P}_drinks_today" "last_drink_at")" ""
expect_eq "Anzeigename deutsch" "$(attr "sensor.${P}_drinks_today" "friendly_name")" "Health-O-Mat ${PERSON} Heute getrunken"
# Tagesziel-Mathe (Ziel unter Buchungssumme → reached on)
"$HA_TEST/bin/ha" POST /api/services/number/set_value "{\"entity_id\": \"number.${P}_daily_goal\", \"value\": 800}" >/dev/null
sleep 1
expect_eq "progress (x/800)" "$(state "sensor.${P}_daily_goal_progress")" "$(python3 -c "print(round((${v0%.*}+833)/800*100, 1))")"
expect_eq "goal_reached on" "$(state "binary_sensor.${P}_daily_goal_reached")" "on"
[ "$(attr "sensor.${P}_lifetime_total" "state_class")" = "total_increasing" ] && pass "lifetime state_class" || fail "lifetime state_class"
expect_ne "lebenszähler > 0" "$(state "sensor.${P}_lifetime_total")" "0"
# Fehlerpfade (HA-REST: HTTP 500, keine Meldung im Body → Zustand muss unverändert bleiben)
pre=$(state "sensor.${P}_drinks_today")
err=$("$HA_TEST/bin/ha" POST /api/services/text/set_value "{\"entity_id\": \"text.${P}_log_drink_free_text\", \"value\": \"blabla ohne menge\"}" 2>&1)
expect_http500 "freitext-fehler (500)" "$err"
expect_state_unchanged "freitext-fehler (keine buchung)" "sensor.${P}_drinks_today" "$pre"
err=$("$HA_TEST/bin/ha" POST /api/services/health_o_mat/add_drink '{"person": "'$PERSON'", "amount_ml": 0}' 2>&1)
expect_http500 "add_drink menge 0 (500)" "$err"
expect_state_unchanged "add_drink menge 0 (keine buchung)" "sensor.${P}_drinks_today" "$pre"
err=$("$HA_TEST/bin/ha" POST /api/services/health_o_mat/add_drink '{"person": "NiemandXYZ", "amount_ml": 250}' 2>&1)
expect_http500 "unbekannte Person (500)" "$err"
expect_state_unchanged "unbekannte Person (keine buchung)" "sensor.${P}_drinks_today" "$pre"
# Undo bis leer → Fehlerpfad (max. 20 Versuche, dann muss der Verlauf leer sein —
# unbegrenzte While-Schleife würde bin/ha-Token-Refreshes sinnlos hämmern)
for i in $(seq 1 20); do
  "$HA_TEST/bin/ha" POST /api/services/button/press "{\"entity_id\": \"button.${P}_undo_last_drink\"}" >/dev/null 2>&1 || break
  [ "$(state "sensor.${P}_drinks_today")" = "0" ] && break
done
expect_eq "verlauf geleert" "$(state "sensor.${P}_drinks_today")" "0"
err=$("$HA_TEST/bin/ha" POST /api/services/health_o_mat/remove_last_entry '{"person": "'$PERSON'"}' 2>&1)
expect_http500 "undo bei leerem Verlauf (500)" "$err"

# ------------------------------------------------------------------ Blutdruck
step "Blutdruck-Batterie"
"$HA_TEST/bin/ha" POST /api/services/number/set_value "{\"entity_id\": \"number.${P}_new_reading_systolic\", \"value\": 128}" >/dev/null
"$HA_TEST/bin/ha" POST /api/services/number/set_value "{\"entity_id\": \"number.${P}_new_reading_diastolic\", \"value\": 84}" >/dev/null
"$HA_TEST/bin/ha" POST /api/services/number/set_value "{\"entity_id\": \"number.${P}_new_reading_pulse\", \"value\": 66}" >/dev/null
sleep 1
expect_eq "input sys persistiert" "$(state "number.${P}_new_reading_systolic")" "128"
"$HA_TEST/bin/ha" POST /api/services/button/press "{\"entity_id\": \"button.${P}_save_measurement\"}" >/dev/null
sleep 1
expect_eq "messung sys" "$(state "sensor.${P}_blood_pressure_systolic")" "128"
expect_eq "messung dia" "$(state "sensor.${P}_blood_pressure_diastolic")" "84"
expect_eq "messung puls" "$(state "sensor.${P}_pulse")" "66"
expect_ne "avg_7d gesetzt" "$(attr "sensor.${P}_blood_pressure_systolic" "avg_7d")" ""
expect_eq "inputs geleert" "$(state "number.${P}_new_reading_systolic")" "unknown"
expect_eq "bp_warning off (128<140)" "$(state "binary_sensor.${P}_blood_pressure_warning")" "off"
expect_json "history_json" "sensor.${P}_blood_pressure_history" "history_json"
pre_bp=$(state "sensor.${P}_blood_pressure_history")
err=$("$HA_TEST/bin/ha" POST /api/services/button/press "{\"entity_id\": \"button.${P}_save_measurement\"}" 2>&1)
expect_http500 "save ohne Eingaben (500)" "$err"
expect_state_unchanged "save ohne Eingaben (keine messung)" "sensor.${P}_blood_pressure_history" "$pre_bp"
# Schwelle senken → warnung muss an
"$HA_TEST/bin/ha" POST /api/services/number/set_value "{\"entity_id\": \"number.${P}_systolic_warning_threshold\", \"value\": 100}" >/dev/null
sleep 1
expect_eq "bp_warning on (128>=100)" "$(state "binary_sensor.${P}_blood_pressure_warning")" "on"
"$HA_TEST/bin/ha" POST /api/services/number/set_value "{\"entity_id\": \"number.${P}_systolic_warning_threshold\", \"value\": 140}" >/dev/null
sleep 1
expect_eq "bp_warning wieder off" "$(state "binary_sensor.${P}_blood_pressure_warning")" "off"
[ "$(attr "sensor.${P}_blood_pressure_systolic" "state_class")" = "measurement" ] && pass "bp state_class" || fail "bp state_class"

# ------------------------------------------------------------------ Wohlbefinden
step "Wohlbefinden-Batterie"
for st in very_bad bad okay good great; do
  "$HA_TEST/bin/ha" POST /api/services/button/press "{\"entity_id\": \"button.${P}_report_${st}\"}" >/dev/null
  sleep 1
  expect_eq "report $st" "$(state "select.${P}_wellbeing")" "$st"
done
expect_ne "emoji gesetzt" "$(attr "select.${P}_wellbeing" "emoji")" ""
expect_ne "reported_at gesetzt" "$(attr "select.${P}_wellbeing" "reported_at")" ""
expect_ne "wellbeing_since gesetzt" "$(state "sensor.${P}_wellbeing_last_reported")" "unknown"
expect_json "wellbeing history" "select.${P}_wellbeing" "history_json"
"$HA_TEST/bin/ha" POST /api/services/select/select_option "{\"entity_id\": \"select.${P}_wellbeing\", \"option\": \"bad\"}" >/dev/null
sleep 1
expect_eq "select raw-key" "$(state "select.${P}_wellbeing")" "bad"

# ------------------------------------------------------------------ Multi-Person
step "Multi-Person-Isolation"
ENTRY2=$(ensure_fresh_person "${PERSON}2")
v1=$(state "sensor.${P}_drinks_today")
"$HA_TEST/bin/ha" POST /api/services/health_o_mat/add_drink '{"person": "'${PERSON}2'", "amount_ml": 1000}' >/dev/null
sleep 1
expect_eq "personen-getrennt" "$(state "sensor.${P}_drinks_today")" "$v1"
pre2=$(state "sensor.${P}2_drinks_today")
err=$("$HA_TEST/bin/ha" POST /api/services/health_o_mat/add_drink '{"amount_ml": 100}' 2>&1)
expect_http500 "mehrdeutigkeit ohne person (500)" "$err"
expect_state_unchanged "mehrdeutigkeit (keine buchung E2E2)" "sensor.${P}2_drinks_today" "$pre2"
if [ "$CLEANUP" = "1" ]; then delete_entry "$ENTRY2"; echo "  cleanup: ${PERSON}2 entfernt"; fi

# ------------------------------------------------------------------ Export
step "CSV-Export"
"$HA_TEST/bin/ha" POST /api/services/health_o_mat/add_drink '{"person": "'$PERSON'", "amount_ml": 500, "drink_type": "Wasser"}' >/dev/null
sleep 1
"$HA_TEST/bin/ha" POST /api/services/health_o_mat/export_csv '{"person": "'$PERSON'", "dataset": "all"}' >/dev/null
docker exec ha-test sh -c 'ls /config/health_o_mat_export/*.csv 2>/dev/null | wc -l' | grep -qE '^[2-9]' && pass "export CSVs vorhanden" || fail "export CSVs vorhanden"

# ------------------------------------------------------------------ Dashboards
step "Dashboard-Referenzen (live)"
"$HA_TEST/bin/check-dashboards" "$REPO/examples/"*.yaml >/dev/null 2>&1 \
  && pass "alle Dashboards aufgelöst" \
  || fail "alle Dashboards aufgelöst (Details: bin/check-dashboards $REPO/examples/*.yaml)"
step "Dashboards laden (Lovelace-Config Save+Load)"
for dash in "dashboard.yaml:hom-standard" "dashboard-mushroom.yaml:hom-mushroom"; do
  f="${dash%%:*}"; up="${dash##*:}"
  if "$HA_TEST/bin/lovelace" save "$up" "$REPO/examples/$f" >/dev/null 2>&1 \
     && "$HA_TEST/bin/lovelace" verify "$up" "$REPO/examples/$f" >/dev/null 2>&1; then
    pass "lovelace $f"
  else
    fail "lovelace $f"
  fi
done

# ---------------------------------------------------------- Update-Migration
if [ "$WITH_MIGRATION" = "1" ]; then
  step "Update-Migration v0.4.0 → aktuell (Worktree)"
  git -C "$REPO" fetch origin v0.4.0 >/dev/null 2>&1 || true
  WT=/tmp/hom-e2e-v040
  git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1 || true
  rm -rf "$WT"
  git -C "$REPO" worktree add --detach "$WT" v0.4.0 >/dev/null 2>&1
  "$HA_TEST/bin/sync" "$WT" >/dev/null 2>&1
  sleep 3
  ALT_ENTRY=$(ensure_fresh_person "Alt")
  "$HA_TEST/bin/ha" POST /api/services/health_o_mat/add_drink '{"person": "Alt", "amount_ml": 400, "drink_type": "Wasser"}' >/dev/null
  sleep 1
  "$HA_TEST/bin/sync" "$REPO" >/dev/null 2>&1
  sleep 3
  docker exec -i ha-test python3 - "$ALT_ENTRY" <<'EOF' > /tmp/hom-e2e-mig.txt
import json, sys
eid = sys.argv[1]
d = json.load(open('/config/.storage/core.config_entries'))
for e in d['data']['entries']:
    if e['entry_id'] == eid:
        print('version:', e['version'])
        print('data:', json.dumps(e['data'], ensure_ascii=False))
        print('options:', sorted((e.get('options') or {}).keys()))
        break
st = json.load(open('/config/.storage/health_o_mat'))['data']['entries'].get(eid, {})
print('drinks:', [(x['ml'], x['type']) for x in st.get('drinks', [])])
EOF
  cat /tmp/hom-e2e-mig.txt | sed 's/^/  /'
  grep -q "version: 2" /tmp/hom-e2e-mig.txt && pass "entry v1→v2 migriert" || fail "entry v1→v2 migriert"
  grep -q '"quick_drinks"\|"options": \[' /tmp/hom-e2e-mig.txt || true
  grep -q "options: \['quick_drinks'\]" /tmp/hom-e2e-mig.txt && pass "quick_drinks in options" || fail "quick_drinks in options"
  grep -q "(400, 'Wasser')" /tmp/hom-e2e-mig.txt && pass "Alt-Daten erhalten" || fail "Alt-Daten erhalten"
  if [ "$CLEANUP" = "1" ]; then delete_entry "$ALT_ENTRY"; echo "  cleanup: Alt entfernt"; fi
  git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1
  rm -rf "$WT"
fi

# ---------------------------------------------------------- Corrupt-Recovery
# Kaputtes JSON handhabt HA nativ (Backup *.corrupt.<isotime> + Repairs-Eintrag);
# wir verifizieren das Verhalten + dass unsere Daten nach Restore zurückkommen.
if [ "$WITH_CORRUPT" = "1" ]; then
  step "Corrupt-Recovery (HA-nativ)"
  BEFORE=$(state "sensor.${P}_drinks_today")
  docker cp ha-test:/config/.storage/health_o_mat /tmp/hom-e2e-health-backup
  docker exec ha-test sh -c "printf 'KAPUTT{{{' > /config/.storage/health_o_mat"
  docker restart ha-test >/dev/null
  for i in $(seq 1 60); do "$HA_TEST/bin/ha" GET /api/ 2>/dev/null | grep -q "API running" && break; sleep 2; done
  sleep 5
  docker exec ha-test sh -c "ls /config/.storage/health_o_mat.corrupt.*" >/dev/null 2>&1 \
    && pass "HA corrupt-backup" || fail "HA corrupt-backup"
  if docker exec -i ha-test python3 <<'EOF' | grep -q storage_corruption
import json
d = json.load(open('/config/.storage/repairs.issue_registry'))
print([i['issue_id'] for i in d['data']['issues'] if 'health' in (i.get('issue_domain') or '')])
EOF
  then pass "repairs-issue"; else fail "repairs-issue"; fi
  expect_eq "leerer Start (heute=0)" "$(state "sensor.${P}_drinks_today")" "0"
  # Restore
  docker cp /tmp/hom-e2e-health-backup ha-test:/config/.storage/health_o_mat
  docker restart ha-test >/dev/null
  for i in $(seq 1 60); do "$HA_TEST/bin/ha" GET /api/ 2>/dev/null | grep -q "API running" && break; sleep 2; done
  sleep 5
  expect_eq "daten restauriert" "$(state "sensor.${P}_drinks_today")" "$BEFORE"
fi

# ------------------------------------------------------------------ Cleanup
if [ "$CLEANUP" = "1" ]; then
  step "Cleanup"
  delete_entry "$ENTRY_ID"
  echo "  cleanup: $PERSON entfernt"
fi

echo
echo "ERGEBNIS: $OK bestanden, $FAIL fehlgeschlagen"
[ "$FAIL" = "0" ]

/**
 * Health-O-Mat — Lovelace Custom Card (L1, MVP).
 *
 * Vanilla Web Component, no build toolchain, no external imports.
 * Self-contained ES2020, delivered bundled by the integration (see frontend.py)
 * and auto-registered as a Lovelace resource.
 *
 * Config (all keys optional). Every switch defaults to ON — precisely:
 *   - the pre-existing display blocks keep their previous defaults (ON), so an
 *     existing dashboard renders unchanged;
 *   - the input blocks added with this schema are a NEW feature and ON by
 *     default (deliberate, per the approved schema "Eingaben an"). An existing
 *     config that does not mention them therefore gains the input blocks.
 *
 *   type: custom:health-o-mat-card
 *   entry_id: <config entry id>   # optional; omitted => person picker via list_persons
 *   person: <service anchor name> # optional; service-call hint for add_drink/undo
 *   # Display blocks
 *   show_person: true             # person dropdown in the header
 *   show_hydration: true          # ring + daily values + pace/streak/caffeine
 *   show_blood_pressure: true     # last reading (+ category/warning)
 *   show_wellbeing: true          # last wellbeing + score + trend
 *   show_blood_pressure_history: true  # BP trend chart (sys/dia)
 *   # Input blocks
 *   show_drinks: true             # quick-drink buttons
 *   show_manual_amounts: true     # preset ml buttons (+ optional free field)
 *   show_blood_pressure_input: true
 *   show_wellbeing_input: true
 *   show_wellbeing_numeric: true  # numeric 1..10 input next to the emojis
 *   wellbeing_confirm: false      # card asks for confirmation before reporting
 *   show_undo: true
 *   # Person binding
 *   person_mode: selector|fixed   # default: fixed with entry_id, else selector
 *   person_filter: [entry_id, person_slug]  # optional whitelist for the picker
 *   default_person: entry_id      # preselected person in selector mode
 *   # Drink selection (keys of the integration's quick drinks) / amounts
 *   drinks: ["glas_wasser", "kaffee"]  # absent/empty/unknown => all
 *   manual_amounts: [200, 500]
 *   allow_custom_amount: true
 *   # Legacy escape hatch (wins over `drinks` and the integration list):
 *   quick_drinks:
 *     - { label: "Glas", ml: 200, emoji: "💧" }
 *
 * `show_blood_pressure_input: true` set EXPLICITLY wins over
 * `show_blood_pressure: false`; otherwise the input follows the display flag.
 *
 * Data flow (no polling, no own timer):
 *   - first `hass` set  -> load health_o_mat/panel_data (resolve entity ids)
 *   - every `hass` set  -> read live values from hass.states[entity_id]
 *   - after a write     -> one silent panel_data reload to refresh derived values
 */

const CARD_TAG = "health-o-mat-card";
const EDITOR_TAG = "health-o-mat-card-editor";
const CARD_VERSION = "0.1.0";

/* Eingebaute Fallback-Getraenke (nur wenn weder `quick_drinks` noch
 * `panel_data.quick_drinks` vorliegen). Die `key`s entsprechen den
 * Server-Defaults (const.DEFAULT_QUICK_DRINKS), damit die `drinks`-Auswahl der
 * Karte auch ohne Backend-Daten funktioniert. */
const DEFAULT_QUICK_DRINKS = [
  { key: "glas_wasser", label: "Glas Wasser", ml: 200, emoji: "\u{1F4A7}" },
  { key: "flasche_wasser", label: "Flasche", ml: 500, emoji: "\u{1F376}" },
  { key: "kaffee", label: "Kaffee", ml: 250, emoji: "\u2615" },
  { key: "saft", label: "Saft", ml: 200, emoji: "\u{1F964}" },
];

/* Material-Design-Icons der Integrations-Quick-Drinks -> Karten-Emoji.
 * Unbekannte Icons fallen auf den neutralen Tropfen zurueck (die Karte zeigt
 * Emoji, die Integrationsliste liefert mdi-Namen). */
const DRINK_ICON_EMOJI = {
  "mdi:glass-water": "\u{1F4A7}",
  "mdi:bottle-water": "\u{1F376}",
  "mdi:coffee": "\u2615",
  "mdi:fruit-citrus": "\u{1F964}",
};
const DEFAULT_DRINK_EMOJI = "\u{1F4A7}";

const WELLBEING_EMOJI = {
  very_bad: "\u{1F62D}",
  awful: "\u{1F616}",
  bad: "\u{1F641}",
  poor: "\u{1F614}",
  okay: "\u{1F610}",
  mixed: "\u{1F615}",
  good: "\u{1F642}",
  very_good: "\u{1F60A}",
  great: "\u{1F604}",
  excellent: "\u{1F929}",
};

/* Wohlbefinden-Skala (Mirror von const.WELLBEING_STATES): aufsteigende
 * Qualitaet, Index + 1 = Score (1 = schlechtester … 10 = bester).
 * Die Karte ist eine eigenstaendige Datei ohne Imports — der Mirror wird
 * deshalb hier gepflegt (Panel: WELLBEING_STATES in panel-base). Der Server
 * liefert die Skala inkl. eigener Bilder als `wellbeing_scale`. */
const WELLBEING_SCALE = [
  { key: "very_bad", label: "Sehr schlecht", emoji: "\u{1F62D}" },
  { key: "awful", label: "Elend", emoji: "\u{1F616}" },
  { key: "bad", label: "Schlecht", emoji: "\u{1F641}" },
  { key: "poor", label: "Mäßig", emoji: "\u{1F614}" },
  { key: "okay", label: "Okay", emoji: "\u{1F610}" },
  { key: "mixed", label: "Durchwachsen", emoji: "\u{1F615}" },
  { key: "good", label: "Gut", emoji: "\u{1F642}" },
  { key: "very_good", label: "Sehr gut", emoji: "\u{1F60A}" },
  { key: "great", label: "Großartig", emoji: "\u{1F604}" },
  { key: "excellent", label: "Ausgezeichnet", emoji: "\u{1F929}" },
];

/* ---- Karten-Konfiguration (docs/PLAN-CARD-CONFIG.md) ---------------------
 * Alle Schalter sind optional; `true` ist der Default. Das gilt bewusst AUCH
 * fuer die Eingabe-Schalter: sie sind eine neue Funktion (Schema: "Eingaben
 * an"), kein Rueckwaertsversprechen — siehe Dateikopf.
 * Die Liste ist die EINZIGE Quelle fuer die Schalter-Namen — sie wird vom
 * Normalisierer und vom Karten-Editor verwendet. */
const CARD_SHOW_KEYS = [
  "show_person",
  "show_hydration",
  "show_blood_pressure",
  "show_blood_pressure_history",
  "show_wellbeing",
  "show_drinks",
  "show_manual_amounts",
  "show_blood_pressure_input",
  "show_wellbeing_input",
  "show_wellbeing_numeric",
  "show_undo",
];

const PERSON_MODES = ["selector", "fixed"];

const DEFAULT_MANUAL_AMOUNTS = [200, 500];
const MIN_AMOUNT_ML = 1;
const MAX_AMOUNT_ML = 10000;

/* Bereichsgrenzen der Blutdruck-Eingabe (Spiegel der Backend-Validierung). */
const BP_SYS_MIN = 40;
const BP_SYS_MAX = 260;
const BP_DIA_MIN = 40;
const BP_DIA_MAX = 260;
const PULSE_MIN = 20;
const PULSE_MAX = 250;

/* Anzahl der Meldungen im kompakten Trend der Karte. */
const WELLBEING_TREND_POINTS = 14;

/* Rückdatierung (REQ-HOM-120): gleiche Zukunfts-Toleranz wie Server/Panel. */
const TS_FUTURE_TOLERANCE_MS = 5 * 60 * 1000;

/* WHO blood-pressure category keys (logic.bp_category) -> friendly label.
 * Unknown/legacy values fall back to the raw value (see bpCategoryLabel). */
const BP_CATEGORY_LABELS = {
  optimal: "Optimal",
  normal: "Normal",
  high_normal: "Hochnormal",
  grade_1: "Hypertonie Grad 1",
  grade_2: "Hypertonie Grad 2",
  grade_3: "Hypertonie Grad 3",
  crisis: "Krise",
};

/* Hydration pace (ws_api.pace_label) -> compact, unobtrusive indicator. */
const PACE_BADGE = {
  goal_reached: { arrow: "\u2713", label: "Ziel erreicht", cls: "good" },
  ahead: { arrow: "\u2191", label: "voraus", cls: "good" },
  on_track: { arrow: "\u2192", label: "auf Kurs", cls: "ok" },
  behind: { arrow: "\u2193", label: "hinten", cls: "warn" },
};

const RING_RADIUS = 42;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

const CARD_CSS = `
  :host { display: block; }
  ha-card {
    background: var(--card-background-color, var(--ha-card-background, #fff));
    color: var(--primary-text-color, #212121);
    border-radius: var(--ha-card-border-radius, 12px);
    overflow: hidden;
  }
  .hom { padding: 16px; display: flex; flex-direction: column; gap: 16px; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .head-title { display: flex; align-items: center; gap: 8px; font-size: 1.1rem; font-weight: 600; min-width: 0; }
  .head-title .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--primary-color, #03a9f4); flex: none; }
  select {
    background: var(--secondary-background-color, #f2f2f2);
    color: var(--primary-text-color, #212121);
    border: 1px solid var(--divider-color, rgba(0,0,0,.12));
    border-radius: 8px; padding: 8px 10px; font-size: 1rem; min-height: 40px;
  }
  .grid { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; }
  .ring { position: relative; width: 128px; height: 128px; flex: none; }
  .ring svg { width: 100%; height: 100%; display: block; }
  .ring-track { fill: none; stroke: var(--divider-color, rgba(0,0,0,.12)); stroke-width: 8; }
  .ring-fill {
    fill: none; stroke: var(--primary-color, #03a9f4); stroke-width: 8; stroke-linecap: round;
    transition: stroke-dashoffset .45s ease;
  }
  .ring-fill.done { stroke: var(--success-color, #43a047); }
  .ring-label {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center; text-align: center; line-height: 1.15;
  }
  .ring-pct { font-size: 1.5rem; font-weight: 700; }
  .ring-sub { font-size: .75rem; color: var(--secondary-text-color, #727272); margin-top: 2px; }
  .stats { display: flex; flex-direction: column; gap: 6px; min-width: 140px; flex: 1 1 140px; }
  .stat { display: flex; justify-content: space-between; gap: 12px; font-size: .95rem; }
  .stat .k { color: var(--secondary-text-color, #727272); }
  .stat .v { font-weight: 600; }
  .pace { display: inline-flex; align-items: center; gap: 4px; font-size: .8rem; font-weight: 600; }
  .pace .arrow { font-size: .9em; line-height: 1; }
  .pace.good { color: var(--success-color, #43a047); }
  .pace.ok { color: var(--secondary-text-color, #727272); }
  .pace.warn { color: var(--error-color, #db4437); }
  .row {
    display: flex; align-items: center; gap: 12px;
    background: var(--secondary-background-color, rgba(0,0,0,.03));
    border-radius: 10px; padding: 10px 12px;
  }
  .row .big { font-size: 1.35rem; font-weight: 700; white-space: nowrap; }
  .row .emoji { font-size: 1.6rem; line-height: 1; }
  .row .label { flex: 1; min-width: 0; }
  .row .sub { font-size: .8rem; color: var(--secondary-text-color, #727272); }
  .row .score { margin-left: auto; font-weight: 700; font-size: .95rem;
    color: var(--primary-color, #03a9f4); white-space: nowrap; }
  .wb-trend { width: 100%; }
  .wb-trend svg { width: 100%; height: auto; display: block; }
  .wb-trend .line { fill: none; stroke: var(--primary-color, #03a9f4); stroke-width: 2;
    stroke-linecap: round; stroke-linejoin: round; }
  .wb-trend .point { fill: var(--card-background-color, #fff);
    stroke: var(--primary-color, #03a9f4); stroke-width: 1.6; }
  .wb-trend .point-current { fill: var(--primary-color, #03a9f4);
    stroke: var(--card-background-color, #fff); stroke-width: 1.8; }
  .bp-chart { width: 100%; }
  .bp-chart .sub, .block .sub { font-size: .8rem; color: var(--secondary-text-color, #727272); }
  .bp-chart svg { width: 100%; height: auto; display: block; }
  .bp-chart .bp-grid { stroke: var(--divider-color, rgba(0,0,0,.12)); stroke-width: 1; }
  .bp-chart .bp-axis { fill: var(--secondary-text-color, #727272); font-size: 9px; }
  .bp-chart .bp-line { fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
  .bp-chart .bp-sys { stroke: var(--error-color, #db4437); }
  .bp-chart .bp-dia { stroke: var(--primary-color, #03a9f4); }
  .bp-chart .bp-sys-dot { fill: var(--error-color, #db4437); }
  .bp-chart .bp-dia-dot { fill: var(--primary-color, #03a9f4); }
  .bp-legend { display: flex; gap: 14px; font-size: .8rem;
    color: var(--secondary-text-color, #727272); }
  .bp-legend .sys { color: var(--error-color, #db4437); font-weight: 600; }
  .bp-legend .dia { color: var(--primary-color, #03a9f4); font-weight: 600; }
  .warn {
    color: var(--error-color, #db4437); font-weight: 600; font-size: .9rem;
    display: flex; align-items: center; gap: 6px;
  }
  .actions { display: flex; flex-wrap: wrap; gap: 10px; }
  button {
    font: inherit; cursor: pointer; min-height: 52px; flex: 1 1 96px;
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
    background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff);
    border: none; border-radius: 12px; padding: 8px 12px; font-weight: 600;
    transition: filter .15s ease, opacity .15s ease; touch-action: manipulation;
  }
  button:hover { filter: brightness(1.08); }
  button:active { transform: scale(.97); }
  button[disabled] { opacity: .55; cursor: default; }
  button .ml { font-size: .75rem; font-weight: 400; opacity: .9; }
  button.ghost {
    background: transparent; color: var(--primary-color, #03a9f4);
    border: 1px solid var(--primary-color, #03a9f4);
  }
  .msg {
    padding: 12px; border-radius: 10px; font-size: .95rem;
    background: var(--secondary-background-color, rgba(0,0,0,.04));
    color: var(--secondary-text-color, #727272);
  }
  .msg.error { color: var(--error-color, #db4437); }
  .banner {
    display: flex; align-items: center; gap: 10px; padding: 10px 12px;
    border-radius: 10px; font-size: .9rem; font-weight: 600;
    background: var(--secondary-background-color, rgba(0,0,0,.04));
    border-left: 4px solid var(--error-color, #db4437);
    color: var(--error-color, #db4437);
  }
  .msg button { margin-top: 10px; flex: none; min-height: 40px; }
  .block { display: flex; flex-direction: column; gap: 10px; }
  .history-list { list-style: none; margin: 0; padding: 0; display: flex;
    flex-direction: column; gap: 4px; }
  .history-item { display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
    min-width: 0; padding: 4px 0; font-size: .8rem;
    border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.08)); }
  .history-item:last-child { border-bottom: none; }
  .history-time { flex: none; font-size: .72rem; color: var(--secondary-text-color, #727272); }
  .history-text { flex: 1 1 120px; min-width: 0; overflow-wrap: anywhere; }
  .history-status { flex: none; font-size: .72rem; font-weight: 600;
    color: var(--error-color, #db4437); }
  .history-item.voided .history-time, .history-item.voided .history-text {
    text-decoration: line-through; opacity: .7; }
  .history-item button { flex: none; min-height: 36px; padding: 6px 10px; font-size: .75rem; }
  .history-confirm { display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
    flex-basis: 100%; font-size: .78rem; }
  @media (max-width: 400px) {
    .history-item button { flex: 1 1 auto; }
    .history-confirm { width: 100%; }
  }
  .form { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
  .form .field { flex: 1 1 84px; min-width: 72px; }
  .form > button { flex: 0 0 auto; min-width: 104px; min-height: 48px; flex-direction: row; }
  .field { display: flex; flex-direction: column; gap: 4px; font-size: .8rem;
    color: var(--secondary-text-color, #727272); min-width: 0; }
  .field input, .field textarea, .custom-amount input, details.note textarea, input[type="number"] {
    width: 100%; box-sizing: border-box; min-height: 48px; padding: 8px 10px;
    font: inherit; font-size: 1rem; border-radius: 10px;
    border: 1px solid var(--divider-color, rgba(0,0,0,.2));
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color, #212121);
  }
  .custom-amount { display: flex; gap: 8px; align-items: stretch; }
  .custom-amount input { flex: 1 1 auto; }
  .custom-amount button { flex: 0 0 auto; min-width: 96px; min-height: 48px; }
  .form-error {
    color: var(--error-color, #db4437); font-size: .85rem;
    display: flex; align-items: center; gap: 6px;
  }
  details.note { border-top: 1px solid var(--divider-color, rgba(0,0,0,.1)); padding-top: 8px; }
  details.note summary {
    cursor: pointer; min-height: 40px; display: flex; align-items: center;
    font-size: .85rem; color: var(--secondary-text-color, #727272);
  }
  details.note textarea { margin-top: 6px; resize: vertical; font-family: inherit; }
  .wb-actions { display: grid; grid-template-columns: repeat(auto-fit, minmax(64px, 1fr)); gap: 8px; }
  .wb-actions button {
    flex: none; min-height: 64px; padding: 6px 2px;
    background: var(--secondary-background-color, rgba(0,0,0,.05));
    color: var(--primary-text-color, #212121);
    border: 1px solid var(--divider-color, rgba(0,0,0,.12));
  }
  .wb-actions button .emoji { font-size: 1.4rem; line-height: 1; }
  .wb-actions button .wb-img { width: 1.6rem; height: 1.6rem; object-fit: cover; border-radius: 50%; }
  .row .wb-img { width: 2rem; height: 2rem; object-fit: cover; border-radius: 50%; flex: none; }
  .wb-actions button .ml { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
  .wb-actions button.active {
    outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 1px;
    background: var(--primary-color, #03a9f4);
    color: var(--text-primary-color, #fff);
  }
  /* Vorgemerkte, noch nicht gemeldete Auswahl (REQ-HOM-114): bewusst anders
   * als der gespeicherte active-Zustand — gestrichelter Primärrahmen. */
  .wb-actions button.pending {
    outline: 2px dashed var(--primary-color, #03a9f4); outline-offset: 1px;
    border-color: var(--primary-color, #03a9f4);
  }
  .wb-confirm { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .wb-confirm .wb-pending-hint {
    flex: 1 1 auto; font-size: .82rem; color: var(--secondary-text-color, #727272);
  }
  @media (max-width: 380px) { .wb-actions button .ml { display: none; } }
  .editor { padding: 12px; display: flex; flex-direction: column; gap: 12px; }
  .editor label { font-size: .85rem; color: var(--secondary-text-color, #727272); }
  .editor input {
    width: 100%; box-sizing: border-box; min-height: 40px; padding: 8px 10px;
    font: inherit; border-radius: 8px; border: 1px solid var(--divider-color, rgba(0,0,0,.2));
    background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121);
  }
  .editor-hint { margin-top: 4px; font-size: .75rem; color: var(--secondary-text-color, #727272); }
  .editor-group { display: flex; flex-direction: column; gap: 6px; }
  .editor-group-title { font-size: .85rem; font-weight: 600; }
  .editor-check {
    display: flex; align-items: center; gap: 8px; min-height: 40px;
    font-size: .9rem; color: var(--primary-text-color, #212121); cursor: pointer;
  }
  .editor-check input { width: 20px; height: 20px; min-height: 0; margin: 0; }
  .editor-check .ml { font-size: .78rem; color: var(--secondary-text-color, #727272); }
  .editor-row { display: flex; align-items: center; gap: 8px; }
  .editor-row input[type="number"] { flex: 1 1 auto; min-height: 40px; }
  .editor-row button {
    flex: 0 0 auto; min-width: 44px; min-height: 40px; padding: 4px 10px;
    flex-direction: row; font-size: .9rem;
  }
  .editor-row button.ghost { background: transparent; }
  .editor-list { display: flex; flex-direction: column; gap: 6px; }
`;

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function toNumber(value, fallback) {
  const n = typeof value === "number" ? value : parseFloat(value);
  return Number.isFinite(n) ? n : fallback;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

/* Defensive Boolean-Aufloesung: akzeptiert echte Booleans und die ueblichen
 * String-Schreibweisen ("on"/"off" aus YAML-Checkboxen). Alles Unbekannte
 * faellt auf `fallback` zurueck — nie ein Render-Crash. */
function toBool(value, fallback) {
  if (value === true || value === false) return value;
  if (typeof value === "string") {
    const text = value.trim().toLowerCase();
    if (text === "true" || text === "on" || text === "yes" || text === "1") return true;
    if (text === "false" || text === "off" || text === "no" || text === "0") return false;
  }
  return fallback;
}

/* `drinks`: Liste von Integrations-Quick-Drink-Keys. Nur nicht-leere Strings
 * zaehlen; Duplikate fallen weg. Kein Array -> leere Auswahl (= alle). */
function normalizeDrinkKeys(value) {
  if (!Array.isArray(value)) return [];
  const keys = [];
  for (const item of value) {
    if (typeof item !== "string") continue;
    const key = item.trim();
    if (key && !keys.includes(key)) keys.push(key);
  }
  return keys;
}

/* `manual_amounts`: positive Ganzzahlen in ml, geklemmt auf 1…10000.
 * Nicht-numerische/≤0-Werte fallen weg; eine leere Liste (oder kein Array)
 * bedeutet den Default [200, 500]. */
function normalizeAmountList(value) {
  if (!Array.isArray(value)) return DEFAULT_MANUAL_AMOUNTS.slice();
  const amounts = [];
  for (const item of value) {
    const number = toNumber(item, NaN);
    if (!Number.isFinite(number) || number <= 0) continue;
    const ml = Math.round(clamp(number, MIN_AMOUNT_ML, MAX_AMOUNT_ML));
    if (!amounts.includes(ml)) amounts.push(ml);
  }
  return amounts.length ? amounts : DEFAULT_MANUAL_AMOUNTS.slice();
}

/* Legacy-Override `quick_drinks: [{label, ml, emoji}]` — defensiv bereinigt. */
function normalizeLegacyQuickDrinks(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((drink) => ({
      label: drink && drink.label ? String(drink.label) : "Getränk",
      ml: toNumber(drink && drink.ml, 0),
      emoji: drink && drink.emoji ? String(drink.emoji) : DEFAULT_DRINK_EMOJI,
    }))
    .filter((drink) => drink.ml > 0);
}

/* Normalisiert die rohe Lovelace-Konfiguration. WICHTIG: die Information,
 * welche Schalter EXPLIZIT gesetzt wurden, bleibt in `explicit` erhalten —
 * nur so kann `show_blood_pressure_input: true` den Anzeige-Schalter
 * `show_blood_pressure: false` uebersteuern. */
function normalizeStringList(value) {
  if (!Array.isArray(value)) return [];
  const out = [];
  for (const item of value) {
    const text = item == null ? "" : String(item).trim();
    if (text && !out.includes(text)) out.push(text);
  }
  return out;
}

function normalizeCardConfig(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  const explicit = new Set(Object.keys(source));
  const flags = {};
  for (const key of CARD_SHOW_KEYS) {
    flags[key] = toBool(source[key], true);
  }
  // Die BD-Eingabe folgt dem Anzeige-Schalter, AUSSER sie ist explizit gesetzt.
  if (!explicit.has("show_blood_pressure_input")) {
    flags.show_blood_pressure_input = flags.show_blood_pressure;
  }
  const entryId = source.entry_id ? String(source.entry_id) : "";
  const requestedMode = source.person_mode ? String(source.person_mode).toLowerCase() : "";
  const personMode = PERSON_MODES.includes(requestedMode)
    ? requestedMode
    : entryId
      ? "fixed"
      : "selector";
  return {
    entryId,
    personMode,
    personFilter: normalizeStringList(source.person_filter),
    defaultPerson: source.default_person ? String(source.default_person) : "",
    person: source.person ? String(source.person) : "",
    flags,
    explicit,
    drinks: normalizeDrinkKeys(source.drinks),
    manualAmounts: normalizeAmountList(source.manual_amounts),
    allowCustomAmount: toBool(source.allow_custom_amount, true),
    quickDrinks: normalizeLegacyQuickDrinks(source.quick_drinks),
    /* REQ-HOM-114: bewusst NICHT in `CARD_SHOW_KEYS` (das sind die reinen
     * `show_*`-Schalter mit Default `true`) — dieser Schalter ist Default
     * `false` und unabhängig von der Panel-/Server-Option. */
    wellbeingConfirm: toBool(source.wellbeing_confirm, false),
    /* Verlauf der letzten 5 Einträge — Default `false` und bewusst NICHT in
     * `CARD_SHOW_KEYS` (die sind reine `show_*`-Schalter mit Default `true`). */
    showHistory: toBool(source.show_history, false),
  };
}

/* Serverseitige Quick-Drink -> Karten-Darstellung. Die Integration liefert
 * `{key,label,ml,icon}` (mdi-Icon); die Karte zeigt Emoji.
 * Der Schluessel ist defensiv: das Backend liefert fuer Eintraege ohne Key
 * einen LEEREN String (nicht `null`/fehlend) — ein leerer Key faellt deshalb
 * ebenfalls auf den stabilen Slot-Namen zurueck (`slot_<index>`). */
function normalizeServerQuickDrinks(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((drink, index) => {
      const icon = drink && drink.icon ? String(drink.icon) : "";
      const rawKey = drink && drink.key != null ? String(drink.key).trim() : "";
      return {
        key: rawKey || `slot_${index}`,
        label: drink && drink.label ? String(drink.label) : "Getränk",
        ml: toNumber(drink && drink.ml, 0),
        emoji:
          (drink && drink.emoji ? String(drink.emoji) : "") ||
          DRINK_ICON_EMOJI[icon] ||
          DEFAULT_DRINK_EMOJI,
      };
    })
    .filter((drink) => drink.ml > 0);
}

function bpCategoryLabel(value) {
  // Friendly label for the known WHO keys; robust for unknown/legacy values.
  const raw = value == null ? "" : String(value);
  const key = raw.trim().toLowerCase();
  return BP_CATEGORY_LABELS[key] || raw;
}

/* Ein Personen-Eintrag passt zu einem Filterwert, wenn entry_id, Slug oder
 * Anzeigename übereinstimmen (case-insensitiv). Leer = kein Filter. */
function personMatchesFilter(person, filter) {
  if (!filter || !filter.length) return true;
  const values = [
    person && person.entry_id,
    person && person.person_slug,
    person && person.display_name,
  ]
    .filter((value) => value != null)
    .map((value) => String(value).toLowerCase());
  return filter.some((item) => values.includes(String(item).toLowerCase()));
}

function filterPersons(persons, filter) {
  const list = Array.isArray(persons) ? persons : [];
  if (!filter || !filter.length) return list.slice();
  return list.filter((person) => personMatchesFilter(person, filter));
}

/* Bild/Emoji eines Wellbeing-Zustands. Eigene Bilder (PNG/JPG/WebP) haben
 * Vorrang; fehlt ein Bild oder lädt es nicht, fällt die Karte auf das Emoji
 * zurück (onerror entfernt das Bild und zeigt den Emoji-Text). */
function wellbeingVisual(state, cls) {
  const css = cls ? String(cls) : "wb-img";
  const emoji = escapeHtml((state && state.emoji) || "\u{1F642}");
  const image = state && state.image ? String(state.image) : "";
  if (!image) {
    return `<span class="emoji" aria-hidden="true">${emoji}</span>`;
  }
  return `<img class="${escapeHtml(css)}" src="${escapeHtml(image)}" alt="" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='inline'" /><span class="emoji" aria-hidden="true" style="display:none">${emoji}</span>`;
}

/* Blutdruck-Verlauf als kompakte Doppellinie (sys/dia). Reine Lese-Anzeige
 * aus `bp.entries` (letzte 30 Messungen). */
function bpHistorySvg(entries) {
  const list = (Array.isArray(entries) ? entries : [])
    .filter((r) => r && Number.isFinite(toNumber(r.sys, NaN)) && Number.isFinite(toNumber(r.dia, NaN)))
    .slice(-30);
  if (list.length < 2) return "";
  const width = 320;
  const height = 128;
  const pad = { top: 10, right: 12, bottom: 20, left: 30 };
  const values = [];
  list.forEach((r) => {
    values.push(toNumber(r.sys, 0), toNumber(r.dia, 0));
  });
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (!Number.isFinite(min) || !Number.isFinite(max)) return "";
  min = Math.floor((min - 10) / 10) * 10;
  max = Math.ceil((max + 10) / 10) * 10;
  if (max <= min) max = min + 10;
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const step = list.length > 1 ? plotW / (list.length - 1) : 0;
  const point = (value, index) => ({
    x: pad.left + index * step,
    y: pad.top + ((max - value) / (max - min)) * plotH,
  });
  const sysCoords = list.map((r, index) => point(toNumber(r.sys, 0), index));
  const diaCoords = list.map((r, index) => point(toNumber(r.dia, 0), index));
  const path = (coords) =>
    coords
      .map((coord, index) => `${index === 0 ? "M" : "L"}${coord.x.toFixed(1)} ${coord.y.toFixed(1)}`)
      .join(" ");
  const grid = [min, Math.round((min + max) / 2), max]
    .map((value) => {
      const y = pad.top + ((max - value) / (max - min)) * plotH;
      return `<line class="bp-grid" x1="${pad.left}" y1="${y.toFixed(1)}" x2="${width - pad.right}" y2="${y.toFixed(1)}"></line><text class="bp-axis" x="${pad.left - 5}" y="${(y + 3).toFixed(1)}" text-anchor="end">${value}</text>`;
    })
    .join("");
  const dots = list
    .map((r, index) => {
      const sys = sysCoords[index];
      const dia = diaCoords[index];
      const when = r.ts ? formatChartDateTime(Date.parse(r.ts)) : "ohne Zeitangabe";
      const title = `${when} \u2013 ${Math.round(toNumber(r.sys, 0))}/${Math.round(toNumber(r.dia, 0))}`;
      return `<circle class="bp-dot bp-sys-dot" cx="${sys.x.toFixed(1)}" cy="${sys.y.toFixed(1)}" r="2.1"><title>${escapeHtml(title)}</title></circle><circle class="bp-dot bp-dia-dot" cx="${dia.x.toFixed(1)}" cy="${dia.y.toFixed(1)}" r="2.1"><title>${escapeHtml(title)}</title></circle>`;
    })
    .join("");
  const first = list[0].ts ? Date.parse(list[0].ts) : NaN;
  const last = list[list.length - 1].ts ? Date.parse(list[list.length - 1].ts) : NaN;
  const xLabels = [];
  if (Number.isFinite(first)) {
    xLabels.push(
      `<text class="bp-axis" x="${pad.left}" y="${height - 6}" text-anchor="start">${escapeHtml(formatChartDate(first))}</text>`
    );
  }
  if (Number.isFinite(last) && last !== first) {
    xLabels.push(
      `<text class="bp-axis" x="${width - pad.right}" y="${height - 6}" text-anchor="end">${escapeHtml(formatChartDate(last))}</text>`
    );
  }
  const summary = `Blutdruck-Verlauf: ${list.length} Messungen, zuletzt ${Math.round(toNumber(list[list.length - 1].sys, 0))}/${Math.round(toNumber(list[list.length - 1].dia, 0))}`;
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(summary)}" preserveAspectRatio="xMidYMid meet">${grid}<path class="bp-line bp-sys" d="${path(sysCoords)}"></path><path class="bp-line bp-dia" d="${path(diaCoords)}"></path>${dots}${xLabels.join("")}</svg>`;
}

/* Score eines Wohlbefinden-Eintrags — DER SERVER IST DIE WAHRHEIT
 * (REQ-HOM-112). Identische Regel wie im Panel (`wellbeingScore` in
 * health-o-mat-panel-base.js):
 * 1. Ist das Feld `score` vorhanden (auch bei `null`), gilt der Server-Wert;
 *    `null`/nicht-numerisch -> KEIN Score (null). Keine clientseitige
 *    Ersatzableitung — der Server liefert bewusst `null`, wenn der Zustand
 *    nicht auf der kanonischen Skala liegt.
 * 2. FEHLT das Feld `score` komplett (aelterer Server), wird der Score
 *    clientseitig aus dem kanonischen Key abgeleitet — EXAKT
 *    (case-sensitiv), wie `logic.wellbeing_score` (Index + 1, aufsteigende
 *    Qualitaet). Unbekannter Key -> null.
 * 3. Der Score muss im Bereich 1..N liegen; alles andere -> null (nie 0 —
 *    0 waere der schlechteste Wert). */
function wellbeingScore(raw) {
  if (!raw || typeof raw !== "object") return null;
  if ("score" in raw) {
    const direct = toNumber(raw.score, NaN);
    if (!Number.isFinite(direct)) return null;
    const rounded = Math.round(direct);
    if (rounded >= 1 && rounded <= WELLBEING_SCALE.length) return rounded;
    return null;
  }
  const key = typeof raw.key === "string" ? raw.key : "";
  const index = WELLBEING_SCALE.findIndex((state) => state.key === key);
  return index >= 0 ? index + 1 : null;
}

/* Verlauf -> verwertbare Punkte. Eintraege ohne verwertbaren Score (kein
 * `score` und kein bekannter `key`) werden uebersprungen; kein Array ->
 * leere Liste (kein Absturz, keine NaN-Koordinaten). */
function wellbeingScorePoints(history) {
  if (!Array.isArray(history)) return [];
  const points = [];
  history.forEach((entry) => {
    if (!entry || typeof entry !== "object") return;
    const score = wellbeingScore(entry);
    if (score == null) return;
    const rawTs = entry.ts == null ? "" : String(entry.ts);
    const parsed = rawTs ? Date.parse(rawTs) : NaN;
    points.push({
      score,
      label: String(entry.label == null ? "" : entry.label),
      ts: Number.isFinite(parsed) ? parsed : null,
    });
  });
  return points;
}

/* Serie des Trends: Historienpunkte + der AKTUELLE Wert als letzter Punkt.
 *
 * Historie-Semantik (store.set_wellbeing): ein Historieneintrag `{ts, status}`
 * bedeutet "bis zu diesem Zeitpunkt galt `status`" — der aktuelle Zustand steht
 * ausschliesslich in `wellbeing` (`status`/`ts`, im WS-Payload `key`/`at`).
 * Der letzte Historienpunkt ist damit der ABGELOESTE Wert; ohne den aktuellen
 * Punkt wuerde die Sparkline am falschen Wert enden (Widerspruch zum Badge).
 *
 * `current` = {score, key, label, at}. Der Score folgt der Regel von
 * `wellbeingScore`: das vorhandene `current.score` ist die Wahrheit (in der
 * Karte der bereits aufgeloeste Score — identisch zum Badge; `null` bedeutet
 * "kein Score" und damit auch kein aktueller Punkt); nur wenn das Feld FEHLT,
 * wird er aus `current.key` abgeleitet (aeltere Payloads ohne `score`).
 * Ohne verwertbaren Score bleibt die Serie = Historie.
 *
 * MARKER: nur der angehaengte aktuelle Punkt traegt `isCurrent: true`; die
 * Historienpunkte tragen das Feld NICHT. Die Sparkline hebt deshalb genau den
 * Punkt hervor, der den aktuellen Wert darstellt — ohne aktuellen Wert
 * (Badge ohne Score) wird KEIN Punkt hervorgehoben und die Sparkline
 * behauptet keinen aktuellen Wert. */
function wellbeingSeries(history, current) {
  const points = wellbeingScorePoints(history);
  const score = wellbeingScore(current);
  if (score == null) return points;
  const rawTs = current && current.at != null ? String(current.at) : "";
  const parsed = rawTs ? Date.parse(rawTs) : NaN;
  const ts = Number.isFinite(parsed) ? parsed : null;
  const last = points.length ? points[points.length - 1] : null;
  // Duplikat vermeiden: gleicher Zeitstempel UND gleicher Score -> der
  // aktuelle Wert ist im Verlauf bereits abgebildet. Dieser Punkt IST dann
  // der aktuelle Wert -> er wird (und nur er) als `isCurrent` markiert.
  if (last && last.ts === ts && last.score === score) {
    last.isCurrent = true;
    return points;
  }
  points.push({
    score,
    label: String(current.label == null ? "" : current.label),
    ts,
    // NUR der angehaengte aktuelle Punkt traegt den Marker — die
    // Historienpunkte sind abgeloeste Werte.
    isCurrent: true,
  });
  return points;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

/* "19.10." — kompakte Achsenbeschriftung. */
function formatChartDate(ts) {
  if (ts == null || !Number.isFinite(ts)) return "";
  const date = new Date(ts);
  if (!Number.isFinite(date.getTime())) return "";
  return `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)}.`;
}

/* "19.10.2026, 14:30 Uhr" — Zeitpunkt fuer die Tooltips. */
function formatChartDateTime(ts) {
  if (ts == null || !Number.isFinite(ts)) return "";
  const date = new Date(ts);
  if (!Number.isFinite(date.getTime())) return "";
  const day = `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)}.${date.getFullYear()}`;
  return `${day}, ${pad2(date.getHours())}:${pad2(date.getMinutes())} Uhr`;
}

/* Kompakte Sparkline der letzten Meldungen (Score 1..N auf Y, Reihenfolge
 * auf X). Reines Lese-Display: kein Zoom, keine Scrollbars, kein Tooltip-JS
 * (die <title>-Elemente liefern die Details je Punkt).
 *
 * Hervorhebung: nur der explizit markierte aktuelle Wert (`isCurrent`) wird
 * betont. Ohne aktuellen Wert (Badge ohne Score) wird KEIN Punkt betont und
 * die aria-label nennt nur den "letzten Wert" — die Sparkline behauptet dann
 * keinen aktuellen Wert. */
function wellbeingTrendSvg(points) {
  const list = Array.isArray(points) ? points : [];
  if (!list.length) return "";
  const width = 320;
  const height = 40;
  const padY = 5;
  const max = WELLBEING_SCALE.length;
  const span = Math.max(1, max - 1);
  const step = list.length > 1 ? width / (list.length - 1) : 0;
  const coords = list.map((point, index) => ({
    x: list.length > 1 ? index * step : width / 2,
    y: padY + ((max - point.score) / span) * (height - 2 * padY),
  }));
  const path = coords
    .map((coord, index) => `${index === 0 ? "M" : "L"}${coord.x.toFixed(1)} ${coord.y.toFixed(1)}`)
    .join(" ");
  const dots = list.map((point, index) => {
    const coord = coords[index];
    const current = point.isCurrent === true;
    const when = point.ts != null ? formatChartDateTime(point.ts) : "ohne Zeitangabe";
    const label = point.label || "Wohlbefinden";
    const title = `${when} \u2013 ${label} (${point.score} / ${max})`;
    const cls = current ? "point point-current" : "point";
    const radius = current ? 3.4 : 2.4;
    return `<circle class="${cls}" cx="${coord.x.toFixed(1)}" cy="${coord.y.toFixed(1)}" r="${radius}"><title>${escapeHtml(title)}</title></circle>`;
  });
  const last = list[list.length - 1];
  // Der aktuelle Punkt ist explizit markiert; ohne ihn ist der letzte Punkt
  // ein abgeloester Historienwert ("letzter Wert", kein "aktuell").
  const currentPoint = list.find((point) => point && point.isCurrent === true) || null;
  const summary = currentPoint
    ? `Wohlbefinden-Trend: ${list.length} Meldung${list.length === 1 ? "" : "en"}, ` +
      `aktuell ${currentPoint.score} von ${max}${currentPoint.label ? ` (${currentPoint.label})` : ""}`
    : `Wohlbefinden-Trend: ${list.length} Meldung${list.length === 1 ? "" : "en"}, ` +
      `letzter Wert ${last.score} von ${max}${last.label ? ` (${last.label})` : ""}`;
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(summary)}" preserveAspectRatio="xMidYMid meet">${coords.length >= 2 ? `<path class="line" d="${path}"></path>` : ""}${dots.join("")}</svg>`;
}

function activeEntryId(config, fallback) {
  if (config && config.entry_id) return config.entry_id;
  return fallback || "";
}

class HealthOMatCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._cfg = null;
    this._cfgSource = null;
    this._hass = null;
    this._data = null;
    this._persons = null;
    this._activeEntry = "";
    this._error = null;
    this._loading = false;
    this._busyMl = null;
    this._busyBp = false;
    this._busyWb = false;
    this._amountError = "";
    this._bpError = "";
    this._wbError = "";
    this._wbScoreDraft = "";
    /* REQ-HOM-114: vorgemerkte, noch nicht gemeldete Wohlbefinden-Auswahl
     * (`{kind: "key"|"score", key, score, ts}`) — nur bei `wellbeing_confirm`. */
    this._wbPending = null;
    /* REQ-HOM-120: Zeitpunkt-Entwürfe der `datetime-local`-Felder (leer =
     * jetzt). Ein Re-Render darf eine getroffene Auswahl nicht verwerfen. */
    this._tsDraft = { "drink-ts": "", "bp-ts": "", "wb-ts": "" };
    /* Fehler einer AKTION (buchen/undo) — eigener Kanal, damit er auch
     * sichtbar bleibt, wenn Daten bereits geladen sind (`_error` ist fuer
     * Ladefehler reserviert). */
    this._actionError = "";
    /* Getippte, noch nicht gesendete BD-Werte. Ein Re-Render (z. B. durch
     * eine Schnellbuchung oder eine Validierungsmeldung) darf sie nicht
     * loeschen — `_bloodPressureInput` setzt sie wieder ein. */
    this._bpDraft = { sys: "", dia: "", pulse: "", note: "" };
    /* Getippte eigene Menge: ueberlebt einen fehlgeschlagenen Submit
     * (Validierung oder Service-Fehler) und wird nach Erfolg geleert. */
    this._amountDraft = "";
    /* Verlauf (REQ-HOM-115): kind -> { entries, error, loading }. Die Liste
     * kommt ausschließlich aus `health_o_mat/list_history` und ist nur bei
     * `show_history` sichtbar. */
    this._history = {};
    this._historyBusy = false;
    this._historyConfirm = null; // { kind, id }
    this._undoBusyKind = "";
    this._renderScheduled = false;
    this._listenersAttached = false;
    this._onCardClick = this._onCardClick.bind(this);
    this._onCardInput = this._onCardInput.bind(this);
    this._onSelectChange = this._onSelectChange.bind(this);
  }

  /* ---- Lovelace card API -------------------------------------------------- */

  static getStubConfig() {
    return { entry_id: "" };
  }

  setConfig(config) {
    if (!config) throw new Error("health-o-mat-card: configuration is required");
    this._config = config;
    // Neu normalisieren (inkl. der explizit gesetzten Schalter).
    this._cfg = null;
    this._cfgSource = null;
    this._data = null;
    this._persons = null;
    this._error = null;
    this._amountError = "";
    this._bpError = "";
    this._wbError = "";
    this._wbScoreDraft = "";
    this._wbPending = null;
    this._tsDraft = { "drink-ts": "", "bp-ts": "", "wb-ts": "" };
    this._actionError = "";
    this._bpDraft = { sys: "", dia: "", pulse: "", note: "" };
    this._amountDraft = "";
    this._history = {};
    this._historyBusy = false;
    this._historyConfirm = null;
    this._undoBusyKind = "";
    this._activeEntry = activeEntryId(config, "");
    this._render();
    if (this._hass) this._loadData();
  }

  /* Grobe Hoehen-Schaetzung fuer Lovelace — aus den AKTIVEN Bloecken
   * abgeleitet statt fix. Mindestens 1 (Kopfzeile). */
  getCardSize() {
    const flags = this._flags();
    let size = 1; // Kopfzeile
    if (flags.show_hydration) size += 2; // Ring + Tageswerte
    if (flags.show_blood_pressure) size += 1;
    if (flags.show_blood_pressure_history) size += 2; // Verlaufsgraph
    if (flags.show_wellbeing) size += 2; // Zeile + Sparkline
    if (flags.show_drinks) size += 1;
    if (flags.show_manual_amounts) size += 1;
    if (flags.show_blood_pressure_input) size += 2; // Formular + Notiz
    if (flags.show_wellbeing_input) size += 3; // 10 Buttons + Zahleneingabe
    if (flags.show_undo) size += 1;
    if (this._configNorm().showHistory) size += 2; // optionale Verlaufslisten
    return Math.max(1, size);
  }

  /* HA's Lovelace card API looks this up on the CLASS (static), not on the
   * element instance: an instance-only `getConfigElement` makes the dashboard
   * show "visual editor not supported" and fall back to raw YAML. */
  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (!this._config) return;
    if (!this._data && !this._loading && !this._error) {
      this._loadData();
      return;
    }
    // Live values come straight from hass.states; just re-render.
    this._scheduleRender();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    /* Lovelace haengt die Karte beim Mounten einer Ansicht ab und wieder an.
     * Die Listener muessen daher hier (neu) registriert werden — eine
     * Registrierung nur im Konstruktor ist nach dem ersten Detach verloren. */
    if (this._listenersAttached) return;
    this.shadowRoot.addEventListener("click", this._onCardClick);
    this.shadowRoot.addEventListener("input", this._onCardInput);
    this.shadowRoot.addEventListener("change", this._onSelectChange);
    this._listenersAttached = true;
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._onCardClick);
    this.shadowRoot.removeEventListener("input", this._onCardInput);
    this.shadowRoot.removeEventListener("change", this._onSelectChange);
    this._listenersAttached = false;
  }

  /* ---- Data --------------------------------------------------------------- */

  async _loadData(silent) {
    if (!this._hass || !this._config) return;
    if (!silent) {
      this._loading = true;
      this._error = null;
      this._render();
    }
    try {
      const cfg = this._configNorm();
      let entryId = cfg.entryId || this._activeEntry || "";
      const needsPersons = cfg.personMode === "selector" || !entryId;
      if (needsPersons) {
        const listRes = await this._hass.callWS({ type: "health_o_mat/list_persons" });
        const persons = (listRes && listRes.persons) || [];
        const allowed = filterPersons(persons, cfg.personFilter);
        this._persons = allowed;
        if (!allowed.length) {
          this._error = cfg.personFilter.length
            ? "Keine Person passt zum konfigurierten Personen-Filter."
            : "Keine Person eingerichtet.";
          this._data = null;
          this._loading = false;
          this._render();
          return;
        }
        if (cfg.personMode === "selector") {
          const known = entryId && allowed.some((p) => p.entry_id === entryId);
          const preferred =
            (cfg.defaultPerson &&
              allowed.find(
                (p) =>
                  p.entry_id === cfg.defaultPerson ||
                  p.person_slug === cfg.defaultPerson ||
                  p.display_name === cfg.defaultPerson
              )) ||
            null;
          entryId = known ? entryId : preferred ? preferred.entry_id : allowed[0].entry_id;
        } else {
          entryId = allowed[0].entry_id;
        }
        /* Wechselt die aktive Person ohne `_onSelectChange` (Person faellt
         * aus Filter/Liste), gehoert die Vormerkung zur alten Person und muss
         * verworfen werden (REQ-HOM-114). */
        if (entryId !== this._activeEntry) {
          this._wbPending = null;
          this._history = {};
          this._historyConfirm = null;
        }
        this._activeEntry = entryId;
      } else {
        this._persons = null;
      }
      const data = await this._hass.callWS({
        type: "health_o_mat/panel_data",
        entry_id: entryId,
      });
      this._data = data || null;
      this._error = this._data ? null : "Keine Daten für diese Person.";
      if (this._data && this._configNorm().showHistory) await this._loadHistory();
      /* Ein erfolgreicher stiller Reload (nach einer Aktion) beendet den
       * Fehlerzustand: eine alte Aktions-Meldung darf nicht stehen bleiben. */
      if (silent && this._data) this._actionError = "";
    } catch (err) {
      this._error = (err && err.message) ? err.message : String(err);
      if (!silent) this._data = null;
    } finally {
      this._loading = false;
      this._render();
    }
  }

  /* ---- Live state helpers ------------------------------------------------- */

  _entity(key) {
    const map = (this._data && this._data.entities) || {};
    return map[key] || "";
  }

  _state(entityId) {
    if (!entityId || !this._hass || !this._hass.states) return undefined;
    return this._hass.states[entityId];
  }

  _stateValue(entityId, fallback) {
    const s = this._state(entityId);
    if (!s || s.state == null) return fallback;
    const v = s.state;
    if (v === "unknown" || v === "unavailable" || v === "") return fallback;
    return v;
  }

  _stateNumber(entityId, fallback) {
    const raw = this._stateValue(entityId, undefined);
    if (raw === undefined) return fallback;
    return toNumber(raw, fallback);
  }

  /* ---- Normalized config -------------------------------------------------- */

  /* Normalisierte Konfiguration (gecacht, bis `_config` ersetzt wird). Wird
   * `_config` von aussen direkt gesetzt (Tests), greift die Neuberechnung. */
  _configNorm() {
    if (!this._cfg || this._cfgSource !== this._config) {
      this._cfg = normalizeCardConfig(this._config);
      this._cfgSource = this._config;
    }
    return this._cfg;
  }

  _flags() {
    return this._configNorm().flags;
  }

  /* ---- Feature areas ------------------------------------------------------ */

  _areas() {
    // Backwards compatible: a missing `areas` payload (old backend) or a
    // missing individual key means "enabled" — only an explicit false hides.
    const base = { drink: true, bp: true, wellbeing: true };
    const raw = this._data && this._data.areas;
    if (raw && typeof raw === "object") {
      for (const key of Object.keys(base)) {
        if (key in raw) base[key] = raw[key] !== false;
      }
    }
    return base;
  }

  /* ---- Actions ------------------------------------------------------------ */

  _servicePerson() {
    // Service-Anker: `data.person` ist der Anzeigename (options.person_display),
    // das Service-Matching läuft aber gegen `entry.data["person"]` — deshalb
    // bevorzugt `data.person_anchor`, Fallback-Reihenfolge:
    // config.person -> data.person_anchor -> data.person.
    if (this._config && this._config.person) return this._config.person;
    if (this._data && this._data.person_anchor) return this._data.person_anchor;
    return (this._data && this._data.person) || "";
  }

  /* Bucht eine Menge. `drinkType` ist das LABEL des Getraenks (Bugfix:
   * ohne `drink_type` landete jede Buchung als "Eigen"); manuelle Mengen
   * uebergeben explizit "Eigen". */
  async _book(ml, drinkType) {
    if (!this._hass || this._busyMl != null) return;
    const value = toNumber(ml, 0);
    if (value <= 0) return;
    const ts = this._readEntryTs("drink-ts");
    if (!ts.ok) {
      this._actionError = ts.error;
      this._render();
      return;
    }
    // Neuer Versuch: eine alte Aktions-Meldung verschwindet sofort.
    this._actionError = "";
    this._busyMl = value;
    this._render();
    try {
      const payload = {
        amount_ml: value,
        drink_type: drinkType ? String(drinkType) : "Eigen",
        person: this._servicePerson(),
      };
      if (ts.iso) payload.ts = ts.iso;
      await Promise.resolve(this._hass.callService("health_o_mat", "add_drink", payload));
      this._actionError = "";
      this._resetTs("drink-ts");
      await this._loadData(true);
    } catch (err) {
      this._actionError = (err && err.message) ? err.message : String(err);
      this._render();
    } finally {
      this._busyMl = null;
      this._render();
    }
  }

  _readInput(role) {
    const el = this.shadowRoot.querySelector(`[data-role="${role}"]`);
    return el && el.value != null ? String(el.value).trim() : "";
  }

  /* Ganzzahl aus einem Eingabefeld; alles andere -> NaN (kein parseInt-Trick,
   * damit "12.5" oder "12abc" NICHT als 12 durchgehen). */
  _readInt(role) {
    const raw = this._readInput(role);
    if (!/^\d+$/.test(raw)) return NaN;
    return Number.parseInt(raw, 10);
  }

  /* ---- Rückdatierung (REQ-HOM-120) ---------------------------------------- */

  /* `datetime-local`-Feld lesen und validieren.
   * Rückgabe `{ ok: true, iso }` (iso "" = jetzt) oder `{ ok: false, error }`. */
  _readEntryTs(role) {
    const raw = this._readInput(role);
    if (!raw) return { ok: true, iso: "" };
    const parsed = new Date(raw);
    if (!Number.isFinite(parsed.getTime())) {
      return { ok: false, error: "Ungültiger Zeitpunkt — bitte Datum und Uhrzeit prüfen." };
    }
    if (parsed.getTime() > Date.now() + TS_FUTURE_TOLERANCE_MS) {
      return {
        ok: false,
        error: "Der Zeitpunkt liegt in der Zukunft (erlaubt sind bis zu 5 Minuten Toleranz).",
      };
    }
    if (parsed.getFullYear() < 1900) {
      return { ok: false, error: "Der Zeitpunkt ist zu alt (frühestens 1900)." };
    }
    return { ok: true, iso: parsed.toISOString() };
  }

  _tsFieldHtml(role) {
    const draft = (this._tsDraft && this._tsDraft[role]) || "";
    return `<label class="field"><span>Zeitpunkt (leer = jetzt)</span>
      <input type="datetime-local" data-role="${role}" value="${escapeHtml(draft)}" />
    </label>`;
  }

  _resetTs(role) {
    if (this._tsDraft) this._tsDraft[role] = "";
    const el = this.shadowRoot.querySelector(`[data-role="${role}"]`);
    if (el) el.value = "";
  }

  async _submitCustomAmount() {
    if (!this._hass || this._busyMl != null) return;
    this._amountError = "";
    const raw = this._readInput("custom-amount");
    // Getippten Wert merken: er darf bei Fehlern nicht verloren gehen.
    this._amountDraft = raw;
    const value = Number.parseInt(raw, 10);
    const valid =
      /^\d+$/.test(raw) && Number.isFinite(value) && value >= MIN_AMOUNT_ML && value <= MAX_AMOUNT_ML;
    if (!valid) {
      this._amountError =
        `Bitte eine ganze Zahl zwischen ${MIN_AMOUNT_ML} und ${MAX_AMOUNT_ML} ml eingeben.`;
      this._render();
      return;
    }
    await this._book(value, "Eigen");
    // `_book` meldet Service-Fehler im Aktions-Kanal und laesst den Entwurf
    // stehen; nur der Erfolg raeumt Feld und Fehlermeldung.
    if (!this._actionError) {
      this._amountDraft = "";
      this._amountError = "";
      this._render();
    }
  }

  async _saveBp() {
    if (!this._hass || this._busyBp) return;
    this._bpError = "";
    const sys = this._readInt("bp-sys");
    const dia = this._readInt("bp-dia");
    const pulseRaw = this._readInput("bp-pulse");
    const pulse = pulseRaw === "" ? null : this._readInt("bp-pulse");
    const note = this._readInput("bp-note");

    const ts = this._readEntryTs("bp-ts");

    let error = "";
    if (!ts.ok) {
      error = ts.error;
    } else if (!Number.isInteger(sys) || sys < BP_SYS_MIN || sys > BP_SYS_MAX) {
      error = `Systolisch: ganze Zahl zwischen ${BP_SYS_MIN} und ${BP_SYS_MAX}.`;
    } else if (!Number.isInteger(dia) || dia < BP_DIA_MIN || dia > BP_DIA_MAX) {
      error = `Diastolisch: ganze Zahl zwischen ${BP_DIA_MIN} und ${BP_DIA_MAX}.`;
    } else if (pulseRaw !== "" && (!Number.isInteger(pulse) || pulse < PULSE_MIN || pulse > PULSE_MAX)) {
      error = `Puls: ganze Zahl zwischen ${PULSE_MIN} und ${PULSE_MAX} — oder leer lassen.`;
    }
    if (error) {
      this._bpError = error;
      this._render();
      return;
    }

    this._busyBp = true;
    this._render();
    try {
      const payload = {
        systolic: sys,
        diastolic: dia,
        person: this._servicePerson(),
      };
      if (pulse != null) payload.pulse = pulse;
      if (note) payload.note = note;
      if (ts.iso) payload.ts = ts.iso;
      await Promise.resolve(
        this._hass.callService("health_o_mat", "add_blood_pressure", payload)
      );
      // Erfolgreich gespeichert: der Entwurf ist erledigt (der naechste
      // Render startet mit leeren Feldern).
      this._bpDraft = { sys: "", dia: "", pulse: "", note: "" };
      this._resetTs("bp-ts");
      await this._loadData(true);
    } catch (err) {
      this._bpError = (err && err.message) ? err.message : String(err);
      this._render();
    } finally {
      this._busyBp = false;
      this._render();
    }
  }

  /* ---- Wohlbefinden-Bestätigung (REQ-HOM-114) ------------------------------ */

  /* Bestätigungsmodus der Karte: unabhängig von der Panel-/Server-Option. */
  _wellbeingConfirmEnabled() {
    return this._configNorm().wellbeingConfirm === true;
  }

  /* Merkt die Auswahl nur vor — gemeldet wird sie erst mit „Übernehmen".
   * Der Zeitpunkt gehört zur Vormerkung (REQ-HOM-120). */
  _stageWellbeing(key, score) {
    const ts = this._readEntryTs("wb-ts");
    if (!ts.ok) {
      this._wbError = ts.error;
      this._render();
      return;
    }
    this._wbPending = {
      /* Personenbezug: die Karte darf eine Vormerkung nur unter der Person
       * anzeigen/übernehmen, für die sie entstanden ist (REQ-HOM-114). */
      entryId: this._activeEntry || "",
      kind: score == null ? "key" : "score",
      key: key == null ? "" : String(key),
      score: score == null ? null : Number(score),
      ts: ts.iso,
    };
    this._wbError = "";
    this._render();
  }

  /* Nur eine Vormerkung der aktuell gewählten Person gilt (REQ-HOM-114). */
  _wbPendingFor() {
    const pending = this._wbPending;
    if (!pending || pending.entryId !== this._activeEntry) return null;
    return pending;
  }

  /* Zahlen-Eingabe: dieselbe Validierung wie `_reportWellbeingScore`, aber
   * ohne Service-Aufruf (Bestätigungsmodus). */
  _stageWellbeingScore(rawScore) {
    const value = toNumber(rawScore, NaN);
    const max = this._wellbeingScale().length;
    if (!Number.isInteger(value) || value < 1 || value > max) {
      this._wbError = `Bitte eine ganze Zahl zwischen 1 und ${max} eingeben.`;
      this._render();
      return;
    }
    this._stageWellbeing("", value);
  }

  async _confirmWellbeing() {
    const pending = this._wbPendingFor();
    if (!pending || this._busyWb) return;
    if (pending.kind === "score") await this._reportWellbeingScore(pending.score, pending.ts);
    else await this._reportWellbeing(pending.key, pending.ts);
  }

  /* `ts`: undefined = aus dem Feld lesen (Sofort-Modus), String = bereits
   * aufgelöster Zeitpunkt der Vormerkung. */
  async _reportWellbeing(key, ts) {
    if (!this._hass || this._busyWb) return;
    const status = key == null ? "" : String(key);
    if (!this._wellbeingScale().some((state) => state.key === status)) return;
    let timestamp = ts;
    if (timestamp === undefined) {
      const read = this._readEntryTs("wb-ts");
      if (!read.ok) {
        this._wbError = read.error;
        this._render();
        return;
      }
      timestamp = read.iso;
    }
    this._busyWb = true;
    this._wbError = "";
    this._render();
    try {
      const payload = { status: status, person: this._servicePerson() };
      if (timestamp) payload.ts = String(timestamp);
      await Promise.resolve(
        this._hass.callService("health_o_mat", "set_wellbeing", payload)
      );
      // Erfolgreich gemeldet: eine vorgemerkte Auswahl ist erledigt.
      this._wbPending = null;
      this._resetTs("wb-ts");
      await this._loadData(true);
    } catch (err) {
      this._wbError = (err && err.message) ? err.message : String(err);
      this._render();
    } finally {
      this._busyWb = false;
      this._render();
    }
  }

  async _reportWellbeingScore(rawScore, ts) {
    if (!this._hass || this._busyWb) return;
    const value = toNumber(rawScore, NaN);
    const max = this._wellbeingScale().length;
    if (!Number.isInteger(value) || value < 1 || value > max) {
      this._wbError = `Bitte eine ganze Zahl zwischen 1 und ${max} eingeben.`;
      this._render();
      return;
    }
    let timestamp = ts;
    if (timestamp === undefined) {
      const read = this._readEntryTs("wb-ts");
      if (!read.ok) {
        this._wbError = read.error;
        this._render();
        return;
      }
      timestamp = read.iso;
    }
    this._busyWb = true;
    this._wbError = "";
    this._render();
    try {
      const payload = { score: value, person: this._servicePerson() };
      if (timestamp) payload.ts = String(timestamp);
      await Promise.resolve(
        this._hass.callService("health_o_mat", "set_wellbeing", payload)
      );
      this._wbScoreDraft = "";
      this._wbPending = null;
      this._resetTs("wb-ts");
      await this._loadData(true);
    } catch (err) {
      this._wbError = (err && err.message) ? err.message : String(err);
      this._render();
    } finally {
      this._busyWb = false;
      this._render();
    }
  }

  async _undo(kind = "drinks") {
    const undoKind = kind === "blood_pressure" || kind === "wellbeing" ? kind : "drinks";
    if (!this._hass || this._busyMl != null || this._undoBusyKind) return;
    if (undoKind === "drinks" && this._data && this._data.undo && this._data.undo.drink === false) {
      return;
    }
    if (undoKind !== "drinks" && !this._historyAvailable(undoKind)) return;
    this._actionError = "";
    this._undoBusyKind = undoKind;
    this._render();
    try {
      await Promise.resolve(
        this._hass.callService("health_o_mat", "remove_last_entry", {
          person: this._servicePerson(),
          kind: undoKind,
        })
      );
      this._actionError = "";
      await this._loadData(true);
    } catch (err) {
      this._actionError = (err && err.message) ? err.message : String(err);
      this._render();
    } finally {
      this._undoBusyKind = "";
      this._render();
    }
  }

  /* ---- Verlauf (REQ-HOM-115) --------------------------------------------- */

  _historyState(kind) {
    if (!this._history[kind]) {
      this._history[kind] = { entries: [], error: "", loading: false, loaded: false };
    }
    return this._history[kind];
  }

  /* Kompakter Verlauf: IMMER inklusive gelöschter Einträge, damit
   * „Wiederherstellen" in der Karte erreichbar bleibt. */
  async _loadHistory() {
    if (!this._hass || !this._activeEntry || !this._configNorm().showHistory) return;
    const entryId = this._activeEntry;
    const kinds = ["drinks", "blood_pressure", "wellbeing"];
    await Promise.all(
      kinds.map(async (kind) => {
        const state = this._historyState(kind);
        state.loading = true;
        state.error = "";
        try {
          const res = await this._hass.callWS({
            type: "health_o_mat/list_history",
            entry_id: entryId,
            kind,
            include_voided: true,
          });
          // Personenwechsel während des Loads: die Antwort gehört zur alten
          // Person und darf die neue Liste nicht überschreiben.
          if (this._activeEntry !== entryId) return;
          state.entries = res && Array.isArray(res.entries) ? res.entries.slice(0, 5) : [];
          state.loaded = true;
        } catch (err) {
          if (this._activeEntry !== entryId) return;
          state.error = (err && err.message) ? err.message : String(err);
          state.loaded = true;
        } finally {
          if (this._activeEntry === entryId) state.loading = false;
        }
      })
    );
    if (this._activeEntry !== entryId) return;
    this._render();
  }

  /* Aktive Einträge vorhanden? Vor dem ersten History-Load dient der
   * `panel_data`-Fallback (Getränke/BD) bzw. der letzte WB-Block. */
  _historyAvailable(kind) {
    const state = this._history[kind];
    if (state && state.loaded && !state.loading) {
      return state.entries.some((entry) => entry && !entry.voided_at);
    }
    if (kind === "drinks") return !(this._data && this._data.undo) || this._data.undo.drink !== false;
    if (kind === "blood_pressure") {
      return !(this._data && this._data.undo) || this._data.undo.blood_pressure !== false;
    }
    return !!(this._data && this._data.wellbeing && (this._data.wellbeing.at || this._data.wellbeing.key));
  }

  _historyConfirmFor(kind, id) {
    const confirm = this._historyConfirm;
    return !!confirm && confirm.kind === kind && confirm.id === String(id);
  }

  _beginHistoryVoid(kind, id) {
    this._historyConfirm = { kind, id: String(id) };
    this._render();
  }

  async _setHistoryEntryVoided(kind, id, restore) {
    if (!this._hass || !this._activeEntry || this._historyBusy) return;
    this._historyBusy = true;
    this._historyConfirm = null;
    this._actionError = "";
    this._render();
    try {
      await this._hass.callWS({
        type: restore ? "health_o_mat/restore_entry" : "health_o_mat/void_entry",
        entry_id: this._activeEntry,
        kind,
        item_id: String(id),
      });
      await this._loadData(true);
    } catch (err) {
      this._actionError = (err && err.message) ? err.message : String(err);
    } finally {
      this._historyBusy = false;
      this._render();
    }
  }

  _historyItemText(kind, entry) {
    if (!entry || typeof entry !== "object") return "";
    if (kind === "drinks") {
      const parts = [];
      if (Number.isFinite(toNumber(entry.ml, NaN))) parts.push(`${Math.round(toNumber(entry.ml, 0))} ml`);
      if (entry.type) parts.push(String(entry.type));
      if (entry.src) parts.push(String(entry.src));
      return parts.join(" \u00B7 ");
    }
    if (kind === "blood_pressure") {
      const parts = [];
      const sys = toNumber(entry.sys, NaN);
      const dia = toNumber(entry.dia, NaN);
      if (Number.isFinite(sys) && Number.isFinite(dia)) parts.push(`${Math.round(sys)}/${Math.round(dia)}`);
      if (Number.isFinite(toNumber(entry.pulse, NaN))) parts.push(`${Math.round(toNumber(entry.pulse, 0))} bpm`);
      if (entry.note) parts.push(String(entry.note));
      return parts.join(" \u00B7 ");
    }
    const scale = this._wellbeingScale();
    const key = String(entry.key || "").toLowerCase();
    const index = scale.findIndex((state) => state.key === key);
    const known = index >= 0 ? scale[index] : null;
    const label = entry.label || (known && known.label) || "Keine Angabe";
    const score = index >= 0 ? index + 1 : null;
    return score != null && known ? `${label} \u00B7 ${score} / ${scale.length}` : label;
  }

  _historyBlock(kind) {
    if (!this._configNorm().showHistory) return "";
    const state = this._history[kind];
    const entries = state && Array.isArray(state.entries) ? state.entries.slice(0, 5) : [];
    const loading = !!(state && state.loading);
    const error = state && state.error
      ? `<div class="form-error" role="alert">${escapeHtml(state.error)}</div>`
      : "";
    const items = entries
      .map((entry) => {
        if (!entry || typeof entry !== "object") return "";
        const id = entry.id == null ? "" : String(entry.id);
        const voided = !!entry.voided_at;
        const when = entry.ts ? this._timeLabel(entry.ts) : "";
        const awaiting = this._historyConfirmFor(kind, id);
        const action = !id
          ? ""
          : awaiting
          ? `<div class="history-confirm" role="group" aria-label="Eintrag löschen bestätigen">
              <span>Wirklich löschen?</span>
              <button data-action="history-void-confirm" data-kind="${escapeHtml(kind)}"
                data-id="${escapeHtml(id)}" aria-label="Löschen bestätigen">Löschen</button>
              <button class="ghost" data-action="history-void-cancel" aria-label="Löschen abbrechen">Abbrechen</button>
            </div>`
          : voided
            ? `<button class="ghost" data-action="history-restore" data-kind="${escapeHtml(kind)}"
                data-id="${escapeHtml(id)}" aria-label="Eintrag wiederherstellen">Wiederherstellen</button>`
            : `<button class="ghost" data-action="history-void" data-kind="${escapeHtml(kind)}"
                data-id="${escapeHtml(id)}" aria-label="Eintrag löschen">Löschen</button>`;
        return `<li class="history-item${voided ? " voided" : ""}">
            <span class="history-time">${escapeHtml(when || "ohne Zeitangabe")}</span>
            <span class="history-text">${escapeHtml(this._historyItemText(kind, entry))}</span>
            ${voided ? `<span class="history-status">gelöscht</span>` : ""}
            ${action}
          </li>`;
      })
      .join("");
    const body = loading
      ? `<div class="msg">Lade Verlauf\u2026</div>`
      : items
        ? `<ul class="history-list">${items}</ul>`
        : `<div class="msg">Keine Einträge.</div>`;
    return `<div class="block history-block" data-history="${escapeHtml(kind)}">
        <div class="sub">Verlauf (letzte 5)</div>
        ${error}${body}
      </div>`;
  }

  /* Getraenke-Quellen in Vorrang-Reihenfolge:
   * 1. Legacy-Override `quick_drinks` der Karte (gewinnt immer),
   * 2. `panel_data.quick_drinks` der Integration, gefiltert nach `drinks`,
   * 3. eingebaute DEFAULT_QUICK_DRINKS (keine Backend-Daten).
   * Eine leere Schnittmenge (oder keine Auswahl) bedeutet "alle" — nie ein
   * leerer Zustand. */
  _quickDrinks() {
    const cfg = this._configNorm();
    if (cfg.quickDrinks.length) return cfg.quickDrinks;
    const server = normalizeServerQuickDrinks(this._data && this._data.quick_drinks);
    const list = server.length ? server : DEFAULT_QUICK_DRINKS;
    if (!cfg.drinks.length) return list;
    const filtered = list.filter((drink) => cfg.drinks.includes(drink.key));
    return filtered.length ? filtered : list;
  }

  /* Wohlbefinden-Skala: serverseitig geliefert (falls vorhanden), sonst der
   * Mirror WELLBEING_SCALE (inkl. Emoji). */
  _wellbeingScale() {
    const server = this._data && Array.isArray(this._data.wellbeing_scale)
      ? this._data.wellbeing_scale
      : [];
    const cleaned = server
      .map((state) => ({
        key: state && state.key != null ? String(state.key) : "",
        label: state && state.label ? String(state.label) : "",
        emoji: state && state.emoji ? String(state.emoji) : "",
        image: state && state.image ? String(state.image) : "",
      }))
      .filter((state) => state.key);
    if (cleaned.length) {
      return cleaned.map((state) => ({
        key: state.key,
        label: state.label || state.key,
        emoji: state.emoji || WELLBEING_EMOJI[state.key] || "\u{1F642}",
        image: state.image || "",
      }));
    }
    return WELLBEING_SCALE;
  }

  /* Aktuell gemeldeter Zustand (Live-Entity nur, wenn ihr Wert selbst ein
   * Skalen-Key ist — die Entity liefert sonst den Zeitstempel). */
  _wellbeingCurrentKey() {
    const scale = this._wellbeingScale();
    const live = this._stateValue(this._entity("wellbeing"), undefined);
    const liveKey = live != null ? String(live).toLowerCase() : "";
    if (scale.some((state) => state.key === liveKey)) return liveKey;
    const wb = (this._data && this._data.wellbeing) || {};
    return String(wb.key || "").toLowerCase();
  }

  /* ---- Events ------------------------------------------------------------- */

  /* Getippte BD-Werte in den Entwurf uebernehmen — OHNE Re-Render (sonst
   * waere das Feld nach jedem Zeichen neu aufgebaut). Der Entwurf wird beim
   * naechsten Render wieder eingesetzt und ueberlebt damit Schnellbuchungen
   * und Validierungsmeldungen. */
  _onCardInput(ev) {
    const target = ev.target;
    if (!target || !target.getAttribute) return;
    const role = target.getAttribute("data-role") || "";
    const value = target.value == null ? "" : String(target.value);
    if (role.endsWith("-ts")) {
      if (this._tsDraft) this._tsDraft[role] = value;
      return;
    }
    if (role === "custom-amount") {
      // Getippte eigene Menge ebenfalls ohne Re-Render merken.
      this._amountDraft = value;
      return;
    }
    if (role === "wb-score") {
      this._wbScoreDraft = value;
      return;
    }
    if (!role.startsWith("bp-")) return;
    if (!this._bpDraft) this._bpDraft = { sys: "", dia: "", pulse: "", note: "" };
    if (role === "bp-sys") this._bpDraft.sys = value;
    else if (role === "bp-dia") this._bpDraft.dia = value;
    else if (role === "bp-pulse") this._bpDraft.pulse = value;
    else if (role === "bp-note") this._bpDraft.note = value;
  }

  _onCardClick(ev) {
    const target = ev.target && ev.target.closest ? ev.target.closest("[data-action]") : null;
    if (!target) return;
    const action = target.getAttribute("data-action");
    if (action === "book") {
      this._book(
        toNumber(target.getAttribute("data-ml"), 0),
        target.getAttribute("data-drink-type")
      );
    } else if (action === "book-custom") {
      this._submitCustomAmount();
    } else if (action === "save-bp") {
      this._saveBp();
    } else if (action === "wellbeing") {
      if (this._wellbeingConfirmEnabled()) {
        this._stageWellbeing(target.getAttribute("data-key"), null);
      } else {
        this._reportWellbeing(target.getAttribute("data-key"));
      }
    } else if (action === "wellbeing-score") {
      if (this._wellbeingConfirmEnabled()) {
        this._stageWellbeingScore(this._readInput("wb-score"));
      } else {
        this._reportWellbeingScore(this._readInput("wb-score"));
      }
    } else if (action === "wellbeing-confirm") {
      this._confirmWellbeing();
    } else if (action === "undo") {
      this._undo(target.getAttribute("data-kind") || "drinks");
    } else if (action === "history-void") {
      this._beginHistoryVoid(
        target.getAttribute("data-kind") || "drinks",
        target.getAttribute("data-id") || ""
      );
    } else if (action === "history-void-confirm") {
      this._setHistoryEntryVoided(
        target.getAttribute("data-kind") || "drinks",
        target.getAttribute("data-id") || "",
        false
      );
    } else if (action === "history-void-cancel") {
      this._historyConfirm = null;
      this._render();
    } else if (action === "history-restore") {
      this._setHistoryEntryVoided(
        target.getAttribute("data-kind") || "drinks",
        target.getAttribute("data-id") || "",
        true
      );
    } else if (action === "retry") {
      this._loadData();
    }
  }

  _onSelectChange(ev) {
    const target = ev.target;
    if (!target || target.tagName !== "SELECT" || target.getAttribute("data-role") !== "person") {
      return;
    }
    const nextEntry = target.value;
    if (nextEntry !== this._activeEntry) {
      /* Personenwechsel: ALLE personenbezogenen Entwuerfe und Fehler
       * verwerfen. Sonst wuerde z. B. ein fuer Person A getippter
       * BD-Entwurf unter Person B gerendert und dort gespeichert. */
      this._bpDraft = null;
      this._amountDraft = "";
      this._bpError = "";
      this._amountError = "";
      this._wbError = "";
      this._wbScoreDraft = "";
      this._wbPending = null;
      this._tsDraft = { "drink-ts": "", "bp-ts": "", "wb-ts": "" };
      this._actionError = "";
      this._history = {};
      this._historyBusy = false;
      this._historyConfirm = null;
      this._undoBusyKind = "";
      this._activeEntry = nextEntry;
    }
    // Personenliste NICHT verwerfen: sie ist noch gueltig, das Dropdown bleibt
    // gefuellt und es braucht keinen zweiten `list_persons`-Roundtrip.
    this._loadData();
  }

  _scheduleRender() {
    if (this._renderScheduled) return;
    /* Nicht in eine offene Bedienung hineinrendern: ein offenes
     * Personen-Dropdown oder ein fokussiertes Eingabefeld (getippte, noch
     * nicht gesendete Werte) wuerde sonst durch ein `hass`-Update geleert. */
    const active = this.shadowRoot.activeElement;
    if (active && (active.tagName === "SELECT" || active.tagName === "INPUT" || active.tagName === "TEXTAREA")) {
      return;
    }
    this._renderScheduled = true;
    const run = () => {
      this._renderScheduled = false;
      this._render();
    };
    if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(run);
    } else {
      setTimeout(run, 16);
    }
  }

  /* ---- Rendering ---------------------------------------------------------- */

  _render() {
    try {
      this.shadowRoot.innerHTML = this._html();
    } catch (err) {
      // Absolute last resort: never let the card break the dashboard.
      this.shadowRoot.innerHTML =
        `<ha-card><div class="hom"><div class="msg error">` +
        `Health-O-Mat: ${escapeHtml(err && err.message ? err.message : err)}</div></div></ha-card>`;
    }
  }

  _html() {
    const style = `<style>${CARD_CSS}</style>`;
    /* Aktionsfehler (buchen/undo) sind ein eigener Kanal: sie muessen auch
     * sichtbar sein, wenn bereits Daten geladen sind — `_error` ist nur fuer
     * Ladefehler (dann steht statt des Bodys die Fehlermeldung). */
    const banner = this._data ? this._actionBanner() : "";
    const body = this._data
      ? this._body()
      : this._error
        ? this._message(this._error, true)
        : this._message("Lade Health-O-Mat\u2026", false);
    return `${style}<ha-card><div class="hom">${this._head()}${banner}${body}</div></ha-card>`;
  }

  _actionBanner() {
    if (!this._actionError) return "";
    return `<div class="banner" role="alert">\u26A0\uFE0F ${escapeHtml(this._actionError)}</div>`;
  }

  _message(text, isError) {
    const retry = isError
      ? `<button class="ghost" data-action="retry">Erneut versuchen</button>`
      : "";
    return `<div class="msg${isError ? " error" : ""}">${escapeHtml(text)}${retry}</div>`;
  }

  _head() {
    const name = (this._data && this._data.person) || "Health-O-Mat";
    const flags = this._flags();
    const cfg = this._configNorm();
    let selector = "";
    if (
      flags.show_person &&
      cfg.personMode === "selector" &&
      this._persons &&
      this._persons.length
    ) {
      const options = this._persons
        .map((p) => {
          const sel = p.entry_id === this._activeEntry ? " selected" : "";
          return `<option value="${escapeHtml(p.entry_id)}"${sel}>${escapeHtml(
            p.display_name || p.entry_id
          )}</option>`;
        })
        .join("");
      selector = `<select data-role="person" aria-label="Person">${options}</select>`;
    }
    return `<div class="head"><div class="head-title"><span class="dot"></span><span class="name">${escapeHtml(
      name
    )}</span></div>${selector}</div>`;
  }

  _body() {
    const areas = this._areas();
    const flags = this._flags();
    const parts = [];
    // Die Integrations-Bereiche (`areas`) sind ein AND mit den Karten-Flags:
    // ein abgeschalteter Integrationsbereich bleibt aus, auch wenn die Karte
    // den Block anzeigen will.
    if (areas.drink && flags.show_hydration) {
      parts.push(this._hydration());
    }
    if (areas.bp && flags.show_blood_pressure) {
      parts.push(this._bloodPressure());
    }
    if (areas.bp && flags.show_blood_pressure_history) {
      parts.push(this._bloodPressureHistory());
    }
    if (areas.wellbeing && flags.show_wellbeing) {
      parts.push(this._wellbeing());
    }
    if (areas.drink && flags.show_drinks) {
      parts.push(this._drinkActions());
    }
    if (areas.drink && flags.show_manual_amounts) {
      parts.push(this._manualAmounts());
    }
    if (areas.bp && flags.show_blood_pressure_input) {
      parts.push(this._bloodPressureInput());
    }
    if (areas.wellbeing && flags.show_wellbeing_input) {
      parts.push(this._wellbeingInput());
    }
    if (areas.bp && flags.show_undo) {
      parts.push(this._undoAction("blood_pressure"));
    }
    if (areas.wellbeing && flags.show_undo) {
      parts.push(this._undoAction("wellbeing"));
    }
    if (areas.drink && flags.show_undo) {
      parts.push(this._undoAction());
    }
    // Optionaler Verlauf (Default aus): kein Block, keine Layout-Sprünge.
    if (areas.drink) parts.push(this._historyBlock("drinks"));
    if (areas.bp) parts.push(this._historyBlock("blood_pressure"));
    if (areas.wellbeing) parts.push(this._historyBlock("wellbeing"));
    return parts.length
      ? parts.join("")
      : this._message("Keine Blöcke aktiviert — Karten-Konfiguration prüfen.", false);
  }

  _hydration() {
    const data = this._data;
    const entDrinks = this._entity("drinks_today");
    const entPercent = this._entity("percent");

    const ml = this._stateNumber(entDrinks, toNumber(data.today && data.today.ml, 0));
    const goal = toNumber(data.goal_ml, 0);
    const percent = this._stateNumber(
      entPercent,
      toNumber(data.today && data.today.percent, goal > 0 ? Math.round((ml / goal) * 100) : 0)
    );
    const shownPercent = Math.round(percent);
    const fill = clamp(percent, 0, 100);
    const offset = RING_CIRCUMFERENCE * (1 - fill / 100);
    const done = percent >= 100 ? " done" : "";
    const yesterday = toNumber(data.today && data.today.yesterday_ml, NaN);
    const count = toNumber(data.today && data.today.count, NaN);
    const streak = this._stateNumber(this._entity("goal_streak"), NaN);
    const caffeine = this._stateNumber(this._entity("caffeine_today"), NaN);
    const shownMl = Math.round(ml);
    const goalText = goal > 0 ? `${Math.round(goal)} ml` : "\u2013";

    const stats = [
      this._paceBadge(),
      `<div class="stat"><span class="k">Ziel</span><span class="v">${goalText}</span></div>`,
      Number.isFinite(count)
        ? `<div class="stat"><span class="k">Buchungen</span><span class="v">${escapeHtml(count)}</span></div>`
        : "",
      Number.isFinite(yesterday)
        ? `<div class="stat"><span class="k">Gestern</span><span class="v">${Math.round(yesterday)} ml</span></div>`
        : "",
      Number.isFinite(streak) && streak >= 1
        ? `<div class="stat"><span class="k">Serie</span><span class="v">${Math.round(streak)} d</span></div>`
        : "",
      Number.isFinite(caffeine) && caffeine > 0
        ? `<div class="stat"><span class="k">Koffein</span><span class="v">${Math.round(caffeine)} mg</span></div>`
        : "",
    ].join("");

    return `
      <div class="grid">
        <div class="ring">
          <svg viewBox="0 0 100 100" role="img" aria-label="${shownPercent}% des Tagesziels">
            <circle class="ring-track" cx="50" cy="50" r="${RING_RADIUS}"></circle>
            <circle class="ring-fill${done}" cx="50" cy="50" r="${RING_RADIUS}"
              stroke-dasharray="${RING_CIRCUMFERENCE.toFixed(2)}"
              stroke-dashoffset="${offset.toFixed(2)}"
              transform="rotate(-90 50 50)"></circle>
          </svg>
          <div class="ring-label">
            <span class="ring-pct">${shownPercent}%</span>
            <span class="ring-sub">${shownMl} / ${goalText}</span>
          </div>
        </div>
        <div class="stats">${stats}</div>
      </div>`;
  }

  _paceBadge() {
    // `today.pace` is a stable string label (or null without a goal). Only a
    // known label renders; anything else (null/absent/unknown) is omitted.
    const pace = this._data && this._data.today ? this._data.today.pace : null;
    const info = pace ? PACE_BADGE[String(pace)] : null;
    if (!info) return "";
    return `<div class="pace ${info.cls}"><span class="arrow" aria-hidden="true">${info.arrow}</span><span>${escapeHtml(info.label)}</span></div>`;
  }

  _bloodPressure() {
    const bp = (this._data && this._data.bp) || {};
    const sys = this._stateNumber(this._entity("bp_sys"), toNumber(bp.sys, NaN));
    const dia = this._stateNumber(this._entity("bp_dia"), toNumber(bp.dia, NaN));
    const pulse = this._stateNumber(this._entity("bp_pulse"), toNumber(bp.pulse, NaN));
    const categoryEntity = this._entity("bp_category");
    const category =
      this._stateValue(categoryEntity, undefined) ||
      (bp.category ? String(bp.category) : "");
    const warning = this._bpWarning();

    const hasReading = Number.isFinite(sys) && Number.isFinite(dia);
    const bigValue = hasReading
      ? `${escapeHtml(Math.round(sys))}/${escapeHtml(Math.round(dia))}`
      : "\u2013";

    const subParts = [];
    if (Number.isFinite(pulse)) subParts.push(`${escapeHtml(Math.round(pulse))} bpm`);
    if (category) subParts.push(escapeHtml(bpCategoryLabel(category)));
    const at = bp.at ? this._timeLabel(bp.at) : "";
    if (at) subParts.push(escapeHtml(at));

    const warningHtml = warning
      ? `<div class="warn"><span aria-hidden="true">\u26A0\uFE0F</span><span>Letzte Messung oberhalb der Schwellen</span></div>`
      : "";

    return `
      <div class="row">
        <span class="emoji" aria-hidden="true">\u{1FA78}</span>
        <div class="label">
          <div class="big">${bigValue}</div>
          <div class="sub">${subParts.join(" \u00B7 ") || "Keine Messung"}</div>
        </div>
      </div>
      ${warningHtml}`;
  }

  _bloodPressureHistory() {
    const bp = (this._data && this._data.bp) || {};
    const svg = bpHistorySvg(bp.entries);
    if (!svg) return "";
    return `<div class="block bp-chart">
      <div class="sub">Blutdruck-Verlauf</div>
      <div class="bp-legend"><span class="sys">Systolisch</span><span class="dia">Diastolisch</span></div>
      ${svg}
    </div>`;
  }

  _bpWarning() {
    const bp = (this._data && this._data.bp) || {};
    if (bp.warning === true) return true;
    // Optional: a warning binary_sensor id, if the backend ever exposes one.
    const warnEntity = this._entity("bp_warning") || this._entity("blood_pressure_warning");
    if (warnEntity) {
      const st = this._stateValue(warnEntity, "");
      if (st === "on" || st === true) return true;
    }
    return false;
  }

  _wellbeing() {
    const wb = (this._data && this._data.wellbeing) || {};
    const scale = this._wellbeingScale();
    const entWb = this._entity("wellbeing");
    const stateRaw = this._stateValue(entWb, undefined);
    const key = String(stateRaw != null ? stateRaw : wb.key || "").toLowerCase();
    /* Anzeige-Key: der Live-State der Entity `wellbeing` ist der Zeitstempel
     * der letzten Meldung — KEIN Wohlbefinden-Key. Als Key taugt er nur,
     * wenn er selbst einer ist; sonst bleibt der (serverseitig lokalisierte)
     * Snapshot die Quelle. */
    const displayKey = scale.some((state) => state.key === key)
      ? key
      : String(wb.key || "").toLowerCase();
    const scaleEntry = scale.find((state) => state.key === displayKey) || {};
    /* Label/Emoji/Bild LIVE-FIRST: liefert die Live-Entity
     * (`entities.wellbeing`) die Attribute `label`/`emoji`/`image`, sind
     * diese aktueller als der (moeglicherweise veraltete) WS-Snapshot. */
    const emoji =
      this._stateAttribute(entWb, "emoji") ||
      wb.emoji ||
      scaleEntry.emoji ||
      WELLBEING_EMOJI[key] ||
      "\u{1F642}";
    const image =
      this._stateAttribute(entWb, "image") || wb.image || scaleEntry.image || "";
    const label =
      this._stateAttribute(entWb, "label") ||
      wb.label ||
      scaleEntry.label ||
      (displayKey ? displayKey.charAt(0).toUpperCase() + displayKey.slice(1) : "Keine Angabe");
    const at = (wb.at && this._timeLabel(wb.at)) || "";

    // Score (1..N): Live-Entity, sonst Server-Feld (der Server ist die
    // Wahrheit: `score: null` bedeutet "kein Score"); nur wenn das Feld
    // fehlt, wird aus dem kanonischen Key abgeleitet (aelterer Payload).
    const scaleMax = scale.length || WELLBEING_SCALE.length;
    const liveScore = this._stateNumber(this._entity("wellbeing_score"), NaN);
    const score =
      Number.isFinite(liveScore) &&
      liveScore >= 1 &&
      liveScore <= scaleMax
        ? Math.round(liveScore)
        : wellbeingScore(wb);
    /* Aktueller Wert als letzter Punkt der Sparkline — mit DEMSELBEN Score wie
     * das Badge (der aufgeloeste `score`), damit Badge und Sparkline nie
     * widersprechen. */
    const current = {
      score: score,
      key: wb.key,
      label: label,
      at: wb.at,
    };
    const points = wellbeingSeries(wb.history, current).slice(-WELLBEING_TREND_POINTS);

    // Leerfall: keine Meldung und keine Historie -> verstaendlicher Hinweis
    // statt eines leeren Charts.
    if (score == null && !points.length) {
      return `
      <div class="row">
        <span class="emoji" aria-hidden="true">\u{1F642}</span>
        <div class="label">
          <div class="big">Keine Angabe</div>
          <div class="sub">Noch keine Wohlbefinden-Meldung</div>
        </div>
      </div>`;
    }

    const scoreBadge =
      score != null
        ? `<span class="score">${score} / ${scaleMax}</span>`
        : "";
    const trend = points.length
      ? `<div class="wb-trend">${wellbeingTrendSvg(points)}</div>`
      : "";
    const sub = at ? `Zuletzt ${escapeHtml(at)}` : "Wohlbefinden";

    return `
      <div class="row">
        ${wellbeingVisual({ emoji, image })}
        <div class="label">
          <div class="big">${escapeHtml(label)}</div>
          <div class="sub">${sub}</div>
        </div>
        ${scoreBadge}
      </div>
      ${trend}`;
  }

  _stateAttribute(entityId, attr) {
    const s = this._state(entityId);
    if (!s || !s.attributes) return "";
    const v = s.attributes[attr];
    return v == null ? "" : v;
  }

  _drinkActions() {
    const busy = this._busyMl != null;
    const buttons = this._quickDrinks()
      .map(
        (drink) => `<button data-action="book" data-ml="${drink.ml}"
            data-drink-type="${escapeHtml(drink.label)}"
            aria-label="${escapeHtml(drink.label)} mit ${Math.round(drink.ml)} Milliliter buchen"${
              busy ? " disabled" : ""
            }>
            <span>${escapeHtml(drink.emoji)} ${escapeHtml(drink.label)}</span>
            <span class="ml">${Math.round(drink.ml)} ml</span>
          </button>`
      )
      .join("");
    const status = busy
      ? `<div class="msg" role="status" aria-live="polite">Buchen\u2026</div>`
      : "";
    return `${this._tsFieldHtml("drink-ts")}<div class="actions">${buttons}</div>${status}`;
  }

  _manualAmounts() {
    const cfg = this._configNorm();
    const flags = cfg.flags;
    const busy = this._busyMl != null;
    const presets = cfg.manualAmounts
      .map(
        (ml) => `<button data-action="book" data-ml="${ml}" data-drink-type="Eigen"
            aria-label="${ml} Milliliter als eigene Menge buchen"${busy ? " disabled" : ""}>
            <span>${ml}</span>
            <span class="ml">ml</span>
          </button>`
      )
      .join("");
    const custom = cfg.allowCustomAmount
      ? `<div class="custom-amount">
          <input type="number" inputmode="numeric" min="${MIN_AMOUNT_ML}"
            max="${MAX_AMOUNT_ML}" step="1" data-role="custom-amount"
            aria-label="Eigene Menge in Milliliter" placeholder="Eigene ml"
            value="${escapeHtml(this._amountDraft || "")}"${busy ? " disabled" : ""} />
          <button data-action="book-custom" aria-label="Eigene Menge buchen"${
            busy ? " disabled" : ""
          }><span>Buchen</span></button>
        </div>`
      : "";
    /* Eigene Live-Region nur, wenn der Getraenke-Block keine rendert (sonst
     * gaebe es zwei identische Ansagen fuer dieselbe Buchung). */
    const drinksStatus = this._areas().drink && flags.show_drinks;
    const status =
      busy && !drinksStatus
        ? `<div class="msg" role="status" aria-live="polite">Buchen\u2026</div>`
        : "";
    const error = this._amountError
      ? `<div class="form-error" role="alert">${escapeHtml(this._amountError)}</div>`
      : "";
    return `<div class="block">${cfg.flags.show_drinks ? "" : this._tsFieldHtml("drink-ts")}<div class="actions">${presets}</div>${custom}${status}${error}</div>`;
  }

  _bloodPressureInput() {
    const busy = this._busyBp === true;
    /* Entwurf wieder einsetzen: ein Re-Render (Schnellbuchung,
     * Validierungsmeldung) darf getippte Werte und die offene Notiz nicht
     * loeschen. */
    const draft = this._bpDraft || { sys: "", dia: "", pulse: "", note: "" };
    const noteOpen = draft.note ? " open" : "";
    const error = this._bpError
      ? `<div class="form-error" role="alert">${escapeHtml(this._bpError)}</div>`
      : "";
    const disabled = busy ? " disabled" : "";
    return `<div class="block">
      ${this._tsFieldHtml("bp-ts")}
      <div class="form">
        <label class="field"><span>Systolisch</span>
          <input type="number" inputmode="numeric" min="${BP_SYS_MIN}" max="${BP_SYS_MAX}"
            step="1" data-role="bp-sys" aria-label="Systolischer Wert"
            value="${escapeHtml(draft.sys)}"${disabled} />
        </label>
        <label class="field"><span>Diastolisch</span>
          <input type="number" inputmode="numeric" min="${BP_DIA_MIN}" max="${BP_DIA_MAX}"
            step="1" data-role="bp-dia" aria-label="Diastolischer Wert"
            value="${escapeHtml(draft.dia)}"${disabled} />
        </label>
        <label class="field"><span>Puls (optional)</span>
          <input type="number" inputmode="numeric" min="${PULSE_MIN}" max="${PULSE_MAX}"
            step="1" data-role="bp-pulse" aria-label="Puls (optional)"
            value="${escapeHtml(draft.pulse)}"${disabled} />
        </label>
        <button data-action="save-bp" aria-label="Blutdruckmessung speichern"${disabled}>
          <span>${busy ? "Speichern\u2026" : "Speichern"}</span>
        </button>
      </div>
      <details class="note"${noteOpen}>
        <summary>Notiz (optional)</summary>
        <textarea data-role="bp-note" rows="2" aria-label="Notiz zur Messung"${disabled}>${escapeHtml(draft.note)}</textarea>
      </details>
      ${busy ? `<div class="msg" role="status" aria-live="polite">Speichern\u2026</div>` : ""}
      ${error}
    </div>`;
  }

  _wellbeingInput() {
    const scale = this._wellbeingScale();
    const active = this._wellbeingCurrentKey();
    const busy = this._busyWb === true;
    const max = scale.length || WELLBEING_SCALE.length;
    /* Bestätigungsmodus (REQ-HOM-114): die vorgemerkte Auswahl wird nur
     * markiert und erst mit „Übernehmen" gemeldet — und nur, wenn sie zur
     * aktuell gewählten Person gehört. */
    const pending = this._wellbeingConfirmEnabled() ? this._wbPendingFor() : null;
    const pendingIndex = pending
      ? pending.kind === "score"
        ? Number.isInteger(pending.score)
          ? pending.score - 1
          : -1
        : scale.findIndex((state) => state.key === pending.key)
      : -1;
    const staged = pendingIndex >= 0 ? scale[pendingIndex] : null;
    const stagedKey = staged ? staged.key : "";
    const pendingScore = pending
      ? pending.kind === "score"
        ? pending.score
        : pendingIndex + 1
      : null;
    const buttons = scale
      .map(
        (state) => `<button class="wb-btn${state.key === active ? " active" : ""}${
          state.key === stagedKey ? " pending" : ""
        }"
            data-action="wellbeing" data-key="${escapeHtml(state.key)}"
            aria-label="Wohlbefinden melden: ${escapeHtml(state.label)}"
            aria-pressed="${state.key === active ? "true" : "false"}"${
              busy ? " disabled" : ""
            }>
            ${wellbeingVisual(state)}
            <span class="ml">${escapeHtml(state.label)}</span>
          </button>`
      )
      .join("");
    const confirmRow = staged
      ? `<div class="wb-confirm">
          <span class="wb-pending-hint">Ausgewählt: ${escapeHtml(staged.label)}${
            pendingScore != null && pendingScore > 0 ? ` (${pendingScore} / ${max})` : ""
          } \u2013 noch nicht gemeldet</span>
          <button data-action="wellbeing-confirm" aria-label="Wohlbefinden-Auswahl übernehmen"${
            busy ? " disabled" : ""
          }><span>Übernehmen</span></button>
        </div>`
      : "";
    const numeric = this._flags().show_wellbeing_numeric
      ? `<div class="custom-amount">
          <input type="number" inputmode="numeric" min="1" max="${max}" step="1"
            data-role="wb-score" aria-label="Wohlbefinden als Zahl (1 bis ${max})"
            placeholder="1\u2013${max}" value="${escapeHtml(this._wbScoreDraft || "")}"${
              busy ? " disabled" : ""
            } />
          <button data-action="wellbeing-score" aria-label="Wohlbefinden als Zahl melden"${
            busy ? " disabled" : ""
          }><span>Zahl melden</span></button>
        </div>`
      : "";
    const error = this._wbError
      ? `<div class="form-error" role="alert">${escapeHtml(this._wbError)}</div>`
      : "";
    const status = busy
      ? `<div class="msg" role="status" aria-live="polite">Melde\u2026</div>`
      : "";
    return `<div class="block">${this._tsFieldHtml("wb-ts")}<div class="actions wb-actions">${buttons}</div>${confirmRow}${numeric}${status}${error}</div>`;
  }

  _undoAction(kind = "drinks") {
    const busy = this._busyMl != null || !!this._undoBusyKind;
    const canUndo = this._historyAvailable(kind);
    // Getränke bleiben als deaktivierter Button sichtbar (bisheriges Layout);
    // BD/WB erscheinen nur, wenn wirklich aktive Einträge existieren.
    if (!canUndo && kind !== "drinks") return "";
    const label =
      kind === "blood_pressure"
        ? "Letzte Blutdruckmessung rückgängig machen"
        : kind === "wellbeing"
          ? "Letzte Wohlbefinden-Meldung rückgängig machen"
          : "Letzte Getränkebuchung rückgängig machen";
    const title = canUndo
      ? ""
      : ' title="Keine Getränkebuchung zum Rückgängigmachen vorhanden"';
    const kindAttr = kind === "drinks" ? "" : ` data-kind="${escapeHtml(kind)}"`;
    const text = kind === "blood_pressure" ? "Undo BD" : kind === "wellbeing" ? "Undo WB" : "Undo";
    return `<div class="actions">
      <button class="ghost" data-action="undo"${kindAttr} aria-label="${escapeHtml(label)}"${
        canUndo ? "" : ' aria-disabled="true"'
      }${title}${busy || !canUndo ? " disabled" : ""}><span aria-hidden="true">\u21A9</span><span class="ml">${text}</span></button>
    </div>`;
  }

  _relativeTime(iso) {
    const ts = Date.parse(iso);
    if (!Number.isFinite(ts)) return "";
    const diffMin = Math.round((Date.now() - ts) / 60000);
    if (diffMin < 1) return "gerade eben";
    if (diffMin < 60) return `vor ${diffMin} min`;
    const hours = Math.round(diffMin / 60);
    if (hours < 24) return `vor ${hours} h`;
    const days = Math.round(hours / 24);
    return `vor ${days} d`;
  }

  /* Anzeige-Zeitpunkt (REQ-HOM-120): relativ für frische Einträge (< 24 h),
   * sonst absolutes Datum/Uhrzeit ("24.10.2026 18:30"). */
  _timeLabel(iso) {
    const ts = Date.parse(iso);
    if (!Number.isFinite(ts)) return "";
    const diff = Date.now() - ts;
    if (diff >= 0 && diff < 24 * 60 * 60 * 1000) return this._relativeTime(iso);
    const date = new Date(ts);
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()} ${pad(
      date.getHours()
    )}:${pad(date.getMinutes())}`;
  }
}

class HealthOMatCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._persons = null;
    this._loading = false;
    this._drinkList = [];
    this._drinksEntry = "";
    this._drinksLoaded = false;
    this._drinksLoading = false;
    this._personFilterEditing = false;
    this._listenersAttached = false;
    this._onValueChange = this._onValueChange.bind(this);
    this._onEditorClick = this._onEditorClick.bind(this);
  }

  setConfig(config) {
    const next = config || {};
    const previous = this._config && this._config.entry_id ? String(this._config.entry_id) : "";
    const current = next.entry_id ? String(next.entry_id) : "";
    this._config = next;
    if (previous !== current) {
      this._drinksEntry = current;
      this._drinksLoaded = false;
      this._drinkList = [];
      this._maybeLoadDrinks();
    }
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    // Populate the person picker once (later hass updates just refresh state).
    if (first && hass) {
      if (this._persons === null) this._loadPersons();
      this._maybeLoadDrinks();
    }
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    /* Symmetrisch zur Karte: der Editor wird von Lovelace ebenfalls ab- und
     * wieder angehaengt. Listener hier (neu) registrieren. */
    if (this._listenersAttached) return;
    this.shadowRoot.addEventListener("input", this._onValueChange);
    this.shadowRoot.addEventListener("change", this._onValueChange);
    this.shadowRoot.addEventListener("click", this._onEditorClick);
    this._listenersAttached = true;
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("input", this._onValueChange);
    this.shadowRoot.removeEventListener("change", this._onValueChange);
    this.shadowRoot.removeEventListener("click", this._onEditorClick);
    this._listenersAttached = false;
  }

  async _loadPersons() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      const res = await this._hass.callWS({ type: "health_o_mat/list_persons" });
      this._persons = (res && res.persons) || [];
    } catch (err) {
      // Never throw into the card editor; fall back to the free entry_id value.
      this._persons = [];
    } finally {
      this._loading = false;
      this._render();
    }
  }

  /* Laedt die konfigurierten Getraenke der gewaehlten Person (nur lesend).
   * Fehler/keine Person -> ruhiger Hinweis, der Editor bleibt bedienbar. */
  _maybeLoadDrinks() {
    const entryId = this._config && this._config.entry_id ? String(this._config.entry_id) : "";
    if (!this._hass || !entryId) return;
    if (this._drinksLoaded && this._drinksEntry === entryId) return;
    this._loadDrinks(entryId);
  }

  async _loadDrinks(entryId) {
    if (!this._hass || !entryId) return;
    /* Ein laufender Ladevorgang wird vom neuen abgeloest: die Antwort wird
     * nur uebernommen, solange sie zur aktuell gewaehlten Person gehoert
     * (sonst ueberschreibt ein spaeter eintreffender Alt-Request die Liste). */
    this._drinksEntry = entryId;
    this._drinksLoaded = false;
    this._drinksLoading = true;
    this._drinkList = [];
    this._render();
    try {
      const res = await this._hass.callWS({
        type: "health_o_mat/panel_data",
        entry_id: entryId,
      });
      if (this._drinksEntry !== entryId) return;
      this._drinkList = normalizeServerQuickDrinks(res && res.quick_drinks);
    } catch (err) {
      // Defensive: editor stays usable, "Alle" remains the default state.
      if (this._drinksEntry !== entryId) return;
      this._drinkList = [];
    } finally {
      if (this._drinksEntry === entryId) {
        this._drinksLoading = false;
        this._drinksLoaded = true;
        this._render();
      }
    }
  }

  _setConfig(next, rerender) {
    this._config = next;
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config: next }, bubbles: true, composed: true })
    );
    if (rerender) this._render();
  }

  _onValueChange(ev) {
    const target = ev.target;
    if (!target) return;
    const role = target.getAttribute ? target.getAttribute("data-role") : "";

    if (role === "amount") {
      // Nur bei `change` (Blur/Enter) uebernehmen — nicht mitten im Tippen.
      if (ev.type !== "change") return;
      this._setAmountFromInput(target);
      return;
    }
    if (role === "drink" || role === "drinks-all") {
      if (ev.type !== "change") return;
      this._toggleDrink(role, target);
      return;
    }
    if (role === "person-filter" || role === "person-filter-all") {
      if (ev.type !== "change") return;
      this._togglePersonFilter(role, target);
      return;
    }
    if (target.tagName !== "INPUT" && target.tagName !== "SELECT") return;
    const key = target.getAttribute("data-key");
    if (!key) return;

    if (target.type === "checkbox") {
      if (ev.type !== "change") return;
      this._toggleFlag(key, target.checked === true);
      return;
    }

    /* Freitext (`person`) und Selects nur bei `change` uebernehmen: ein
     * `input`-Event je Tastendruck feuert `config-changed`, worauf Lovelace
     * `setConfig()` aufruft und das Feld mitten im Tippen neu aufbaut. */
    if (ev.type !== "change") return;

    const next = Object.assign({}, this._config);
    next[key] = target.value;
    if (key === "person_mode") {
      const mode = String(target.value || "");
      this._personFilterEditing = false;
      if (mode === "selector") {
        delete next.entry_id;
      } else if (!next.entry_id && this._persons && this._persons.length) {
        next.entry_id = this._persons[0].entry_id;
      }
      this._config = next;
      this._setConfig(next, true);
      return;
    }
    if (key === "entry_id") {
      // Die Getraenke-Auswahl gehoert zur Person — bei Personenwechsel
      // verwerfen und neu laden.
      const previous = this._config.entry_id ? String(this._config.entry_id) : "";
      if (previous !== String(target.value || "")) delete next.drinks;
      this._drinksEntry = String(target.value || "");
      this._drinksLoaded = false;
      this._drinkList = [];
      // Vor dem Laden uebernehmen, damit `_maybeLoadDrinks` die NEUE Person liest.
      this._config = next;
      this._maybeLoadDrinks();
    }
    this._setConfig(next, key === "entry_id");
  }

  _toggleFlag(key, checked) {
    const next = Object.assign({}, this._config);
    if (key === "wellbeing_confirm" || key === "show_history") {
      /* Default ist `false` (anders als die `show_*`-Schalter): an muss
       * explizit gesetzt werden, aus entfernt den Key wieder. */
      if (checked) next[key] = true;
      else delete next[key];
      this._setConfig(next, true);
      return;
    }
    if (key === "allow_custom_amount") {
      if (checked) delete next[key];
      else next[key] = false;
    } else if (checked) {
      // `true` ist der Default — Rauschen vermeiden. Ausnahme: die BD-Eingabe
      // muss explizit `true` bleiben, wenn die BD-Anzeige aus ist (sonst
      // wuerde sie beim naechsten Laden wieder ausgeblendet).
      if (
        key === "show_blood_pressure_input" &&
        toBool(next.show_blood_pressure, true) === false
      ) {
        next[key] = true;
      } else {
        delete next[key];
      }
    } else {
      next[key] = false;
    }
    this._setConfig(next, true);
  }

  _toggleDrink(role, target) {
    const allKeys = this._drinkList.map((drink) => drink.key);
    if (!allKeys.length) return;
    const next = Object.assign({}, this._config);

    if (role === "drinks-all") {
      if (!target.checked) {
        // "Alle" ist der Zustand OHNE `drinks`-Key — nicht abwaehlbar.
        this._render();
        return;
      }
      delete next.drinks;
      this._setConfig(next, true);
      return;
    }

    const key = target.getAttribute("data-key") || "";
    if (!key) return;
    let selected = this._selectedDrinkKeys();
    if (target.checked) {
      if (!selected.includes(key)) selected.push(key);
    } else {
      selected = selected.filter((item) => item !== key);
    }
    // Nie ein leerer Zustand: letzte Auswahl zurueck auf "alle".
    if (!selected.length) selected = allKeys;
    const ordered = allKeys.filter((item) => selected.includes(item));
    if (ordered.length === allKeys.length) delete next.drinks;
    else next.drinks = ordered;
    this._setConfig(next, true);
  }

  _personFilterValues() {
    return normalizeStringList(this._config.person_filter);
  }

  _togglePersonFilter(role, target) {
    const persons = this._persons || [];
    const allKeys = persons.map((person) => person.entry_id).filter(Boolean);
    if (!allKeys.length) return;
    const next = Object.assign({}, this._config);
    if (role === "person-filter-all") {
      if (target.checked) {
        this._personFilterEditing = false;
        delete next.person_filter;
      } else {
        // "Alle" abwählen = Filter-Modus starten: individuelle Boxen werden
        // sichtbar/aktiv, zunächst ohne Auswahl.
        this._personFilterEditing = true;
        delete next.person_filter;
      }
      this._setConfig(next, true);
      return;
    }
    const key = target.getAttribute("data-key") || "";
    if (!key) return;
    let selected = this._personFilterValues();
    if (target.checked) {
      if (!selected.includes(key)) selected.push(key);
    } else {
      selected = selected.filter((item) => item !== key);
    }
    this._personFilterEditing = false;
    if (selected.length === allKeys.length) delete next.person_filter;
    else next.person_filter = selected;
    this._setConfig(next, true);
  }

  _setAmountFromInput(target) {
    const index = Number.parseInt(target.getAttribute("data-index"), 10);
    if (!Number.isInteger(index) || index < 0) return;
    const amounts = this._editorAmounts().slice();
    if (index >= amounts.length) return;
    const raw = String(target.value == null ? "" : target.value).trim();
    if (!/^\d+$/.test(raw)) {
      this._render();
      return;
    }
    amounts[index] = Math.round(clamp(Number.parseInt(raw, 10), MIN_AMOUNT_ML, MAX_AMOUNT_ML));
    const next = Object.assign({}, this._config, { manual_amounts: amounts });
    this._setConfig(next, true);
  }

  _onEditorClick(ev) {
    const target = ev.target && ev.target.closest ? ev.target.closest("[data-role]") : null;
    if (!target) return;
    const role = target.getAttribute("data-role");
    if (role !== "amount-add" && role !== "amount-remove") return;
    const amounts = this._editorAmounts().slice();
    if (role === "amount-add") {
      const candidates = [200, 250, 300, 330, 400, 500, 750, 1000];
      const next = candidates.find((value) => !amounts.includes(value)) || 200;
      amounts.push(next);
    } else {
      const index = Number.parseInt(target.getAttribute("data-index"), 10);
      if (!Number.isInteger(index) || index < 0 || index >= amounts.length) return;
      amounts.splice(index, 1);
    }
    const nextConfig = Object.assign({}, this._config, { manual_amounts: amounts });
    this._setConfig(nextConfig, true);
  }

  /* Effektive Mengenliste des Editors (leer -> Default 200/500). */
  _editorAmounts() {
    return normalizeAmountList(this._config.manual_amounts);
  }

  _effectiveFlag(key) {
    if (Object.prototype.hasOwnProperty.call(this._config, key)) {
      return toBool(this._config[key], true);
    }
    if (key === "show_blood_pressure_input") {
      return this._effectiveFlag("show_blood_pressure");
    }
    return true;
  }

  _effectiveAllowCustomAmount() {
    return Object.prototype.hasOwnProperty.call(this._config, "allow_custom_amount")
      ? toBool(this._config.allow_custom_amount, true)
      : true;
  }

  /* REQ-HOM-114: eigener Default (`false`) — `_effectiveFlag` liefert `true`. */
  _effectiveWellbeingConfirm() {
    return toBool(this._config.wellbeing_confirm, false);
  }

  _selectedDrinkKeys() {
    const allKeys = this._drinkList.map((drink) => drink.key);
    const configured = normalizeDrinkKeys(this._config.drinks);
    if (!configured.length) return allKeys;
    const known = configured.filter((key) => allKeys.includes(key));
    return known.length ? known : allKeys;
  }

  _personOptions(current) {
    const options = [];
    const auto = current ? "" : " selected";
    options.push(
      `<option value=""${auto}>Automatisch (Personenauswahl in der Karte)</option>`
    );
    let hasCurrent = !current;
    for (const person of this._persons || []) {
      const value = person && person.entry_id ? String(person.entry_id) : "";
      if (!value) continue;
      const selected = value === current ? " selected" : "";
      if (selected) hasCurrent = true;
      const label = (person && (person.display_name || person.entry_id)) || value;
      options.push(
        `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(label)}</option>`
      );
    }
    // Keep an already-configured id visible while the list loads/if it vanished.
    if (!hasCurrent) {
      options.push(`<option value="${escapeHtml(current)}" selected>${escapeHtml(current)}</option>`);
    }
    return options.join("");
  }

  _checkbox(key, label) {
    const checked = this._effectiveFlag(key) ? " checked" : "";
    return `<label class="editor-check">
      <input type="checkbox" data-key="${key}"${checked} />
      <span>${escapeHtml(label)}</span>
    </label>`;
  }

  _displaySection() {
    return `<div class="editor-group">
      <div class="editor-group-title">Anzeige</div>
      ${this._checkbox("show_person", "Personenauswahl")}
      ${this._checkbox("show_hydration", "Trinkmenge (Ring und Tageswerte)")}
      ${this._checkbox("show_blood_pressure", "Letzte Blutdruckmessung")}
      ${this._checkbox("show_blood_pressure_history", "Blutdruck-Verlaufsgraph")}
      ${this._checkbox("show_wellbeing", "Letztes Wohlbefinden")}
    </div>`;
  }

  _inputSection() {
    return `<div class="editor-group">
      <div class="editor-group-title">Eingabe &amp; Aktionen</div>
      ${this._checkbox("show_drinks", "Schnellbuchung Getränke")}
      ${this._checkbox("show_manual_amounts", "Manuelle Mengen")}
      ${this._checkbox("show_blood_pressure_input", "Blutdruck eingeben")}
      ${this._checkbox("show_wellbeing_input", "Wohlbefinden melden")}
      ${this._checkbox("show_wellbeing_numeric", "Wohlbefinden auch als Zahl (1–10)")}
      <label class="editor-check">
        <input type="checkbox" data-key="wellbeing_confirm"${this._effectiveWellbeingConfirm() ? " checked" : ""} />
        <span>Wohlbefinden: Bestätigung vor Übernahme</span>
      </label>
      ${this._checkbox("show_undo", "Letzte Buchung rückgängig")}
      <label class="editor-check">
        <input type="checkbox" data-key="show_history"${toBool(this._config.show_history, false) ? " checked" : ""} />
        <span>Verlauf anzeigen (letzte 5)</span>
      </label>
    </div>`;
  }

  _personSection() {
    const current = this._config.entry_id ? String(this._config.entry_id) : "";
    const mode = String(this._config.person_mode || (current ? "fixed" : "selector"));
    const filter = this._personFilterValues();
    const persons = this._persons || [];
    const allKeys = persons.map((person) => person.entry_id).filter(Boolean);
    const filterIsAll =
      (filter.length === 0 && !this._personFilterEditing) ||
      (allKeys.length > 0 && filter.length === allKeys.length);
    const selected = filter.length ? filter : filterIsAll ? allKeys : [];
    const rows = persons
      .map((person) => {
        const key = person && person.entry_id ? String(person.entry_id) : "";
        if (!key) return "";
        const checked = selected.includes(key) ? " checked" : "";
        const disabled = filterIsAll ? " disabled" : "";
        const label = (person && (person.display_name || person.entry_id)) || key;
        return `<label class="editor-check">
          <input type="checkbox" data-role="person-filter" data-key="${escapeHtml(key)}"${checked}${disabled} />
          <span>${escapeHtml(label)}</span>
        </label>`;
      })
      .join("");
    const filterBlock =
      mode !== "selector"
        ? `<div class="editor-hint">Fest gebunden — der Dropdown-Filter wird ignoriert.</div>`
        : persons.length
          ? `<label class="editor-check">
              <input type="checkbox" data-role="person-filter-all"${filterIsAll ? " checked" : ""} />
              <span>Alle Personen im Dropdown</span>
            </label>${rows}
            <div class="editor-hint">„Alle Personen“ abwählen, um einzelne Personen fürs Dropdown auszuwählen.</div>`
          : `<div class="editor-hint">Personenliste wird geladen\u2026</div>`;
    return `<div class="editor-group">
      <div class="editor-group-title">Personen-Bindung</div>
      <div class="editor-row">
        <select data-key="person_mode" aria-label="Personen-Modus">
          <option value="selector"${mode === "selector" ? " selected" : ""}>Dropdown (Personenauswahl)</option>
          <option value="fixed"${mode === "fixed" ? " selected" : ""}>Fest an eine Person gebunden</option>
        </select>
      </div>
      ${filterBlock}
    </div>`;
  }

  _drinksSection() {
    const entryId = this._config.entry_id ? String(this._config.entry_id) : "";
    const head = `<div class="editor-group-title">Getränke</div>`;
    if (!entryId) {
      return `<div class="editor-group">${head}
        <div class="editor-hint">Person wählen, um Getränke zu laden. Ohne eigene Auswahl erscheinen alle Getränke der Person.</div>
      </div>`;
    }
    if (this._drinksLoading) {
      return `<div class="editor-group">${head}
        <div class="editor-hint">Getränke werden geladen\u2026</div>
      </div>`;
    }
    if (!this._drinkList.length) {
      return `<div class="editor-group">${head}
        <div class="editor-hint">Getränke konnten nicht geladen werden — es erscheinen alle Getränke der Person.</div>
      </div>`;
    }
    const selected = this._selectedDrinkKeys();
    const allSelected = selected.length === this._drinkList.length;
    const allBox = `<label class="editor-check">
      <input type="checkbox" data-role="drinks-all"${allSelected ? " checked" : ""} />
      <span>Alle Getränke</span>
    </label>`;
    const rows = this._drinkList
      .map(
        (drink) => `<label class="editor-check">
          <input type="checkbox" data-role="drink" data-key="${escapeHtml(drink.key)}"${
            selected.includes(drink.key) ? " checked" : ""
          } />
          <span>${escapeHtml(drink.label)} <span class="ml">${Math.round(drink.ml)} ml</span></span>
        </label>`
      )
      .join("");
    return `<div class="editor-group">${head}${allBox}${rows}
      <div class="editor-hint">Ohne eigene Auswahl erscheinen alle Getränke.</div>
    </div>`;
  }

  _amountsSection() {
    const amounts = this._editorAmounts();
    const rows = amounts
      .map(
        (ml, index) => `<div class="editor-row">
          <input type="number" inputmode="numeric" min="${MIN_AMOUNT_ML}"
            max="${MAX_AMOUNT_ML}" step="1" data-role="amount" data-index="${index}"
            value="${ml}" aria-label="Menge ${index + 1} in Milliliter" />
          <button class="ghost" type="button" data-role="amount-remove" data-index="${index}"
            aria-label="Menge ${ml} Milliliter entfernen">\u2715</button>
        </div>`
      )
      .join("");
    return `<div class="editor-group">
      <div class="editor-group-title">Manuelle Mengen (ml)</div>
      <div class="editor-list">${rows}</div>
      <div class="editor-row">
        <button class="ghost" type="button" data-role="amount-add"
          aria-label="Weitere Menge hinzufügen"><span>Menge hinzufügen</span></button>
      </div>
      <label class="editor-check">
        <input type="checkbox" data-key="allow_custom_amount"${
          this._effectiveAllowCustomAmount() ? " checked" : ""
        } />
        <span>Freies Zahlenfeld erlauben</span>
      </label>
      <div class="editor-hint">Ohne eigene Mengen gelten 200 und 500 ml.</div>
    </div>`;
  }

  _render() {
    const current = this._config.entry_id ? String(this._config.entry_id) : "";
    let hint = "";
    if (this._persons === null) {
      hint = this._loading ? "Personen werden geladen\u2026" : "";
    } else if (!this._persons.length) {
      hint = "Keine Person eingerichtet \u2014 Karte nutzt den freien person-Anker.";
    }
    const mode = String(this._config.person_mode || (current ? "fixed" : "selector"));
    const personPicker =
      mode === "fixed"
        ? `<div>
            <label for="entry_id">Feste Person</label>
            <select id="entry_id" data-key="entry_id">${this._personOptions(current)}</select>
            ${hint ? `<div class="editor-hint">${escapeHtml(hint)}</div>` : ""}
          </div>`
        : `<div class="editor-hint">Dropdown-Modus: Die angezeigten Personen werden im Abschnitt „Personen-Bindung“ gefiltert.</div>`;
    this.shadowRoot.innerHTML = `
      <style>${CARD_CSS}</style>
      <div class="editor">
        ${personPicker}
        <div>
          <label for="person">person \u2014 optionaler Service-Anker</label>
          <input id="person" data-key="person" type="text"
            value="${escapeHtml(this._config.person || "")}" placeholder="z. B. Caro" />
          <div class="editor-hint">Leer lassen, wenn die Karte \u00fcber die gew\u00e4hlte Person schreiben soll. Nur n\u00f6tig, wenn ein abweichender Anker (entry.data \u201eperson\u201c) angesprochen werden muss.</div>
        </div>
        ${this._personSection()}
        ${this._displaySection()}
        ${this._inputSection()}
        ${this._drinksSection()}
        ${this._amountsSection()}
      </div>`;
  }
}

if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, HealthOMatCard);
}
if (!customElements.get(EDITOR_TAG)) {
  customElements.define(EDITOR_TAG, HealthOMatCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c && c.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "Health-O-Mat",
    description:
      "Trinkmenge, Blutdruck und Wohlbefinden auf einen Blick — mit Quick-Buchung und Undo.",
    preview: false,
    documentationURL: "https://github.com/Popoboxxo/ha-health-o-mat",
  });
}

console.info(
  `%c HEALTH-O-MAT-CARD %c v${CARD_VERSION} `,
  "color:#fff;background:#03a9f4;font-weight:700;border-radius:3px 0 0 3px",
  "color:#03a9f4;background:#fff;font-weight:700;border-radius:0 3px 3px 0"
);

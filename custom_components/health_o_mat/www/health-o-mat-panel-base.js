/**
 * Health-O-Mat — Panel base module.
 *
 * Leaf module of the panel's native ES-module split: no imports, only the
 * shared constants, WebSocket command names, the component CSS and pure
 * helpers (formatting, parsing, area + person lookups) reused by the views and
 * admin modules.
 *
 * Cache-busting: the module is served with `cache_headers=True`; every import
 * specifier in sibling panel modules therefore carries the integration version
 * as a query parameter (kept in sync with manifest.json by tests/test_panel_js.py).
 */

/* --- panel identity ------------------------------------------------------- */

/* Kept in the entry module: `PANEL_TAG` is the registered webcomponent name. */

/* --- static data ---------------------------------------------------------- */

/* Quick drinks for the "Trinken" tab. `type` is the canonical drink label
 * stored on the drink (`store.add_drink`), used for the caffeine breakdown. */
export const QUICK_DRINKS = [
  { label: "Glas Wasser", ml: 200, emoji: "\u{1F4A7}", type: "Wasser" },
  { label: "Flasche", ml: 500, emoji: "\u{1F376}", type: "Wasser" },
  { label: "Kaffee", ml: 250, emoji: "\u2615", type: "Kaffee" },
  { label: "Saft", ml: 200, emoji: "\u{1F964}", type: "Saft" },
];

/* Wellbeing taps (mirrors const.WELLBEING_STATES). */
export const WELLBEING_STATES = [
  { key: "very_bad", label: "Sehr schlecht", emoji: "\u{1F635}" },
  { key: "bad", label: "Schlecht", emoji: "\u{1F641}" },
  { key: "okay", label: "Okay", emoji: "\u{1F610}" },
  { key: "good", label: "Gut", emoji: "\u{1F642}" },
  { key: "great", label: "Super", emoji: "\u{1F604}" },
];

/* WHO blood-pressure category keys (logic.bp_category) -> label + colour. */
export const BP_CATEGORIES = {
  optimal: { label: "Optimal", cls: "good" },
  normal: { label: "Normal", cls: "good" },
  high_normal: { label: "Hochnormal", cls: "ok" },
  grade_1: { label: "Hypertonie Grad 1", cls: "warn" },
  grade_2: { label: "Hypertonie Grad 2", cls: "warn" },
  grade_3: { label: "Hypertonie Grad 3", cls: "bad" },
  crisis: { label: "Krise", cls: "bad" },
};

/* Pace labels (ws_api.compute_pace). */
export const PACE_INFO = {
  goal_reached: { text: "Tagesziel erreicht", cls: "good" },
  ahead: { text: "Auf Kurs (voraus)", cls: "good" },
  on_track: { text: "Auf Kurs", cls: "ok" },
  behind: { text: "Zu langsam", cls: "warn" },
};

/* WebSocket commands. Admin-only ones are server-gated as well (see the entry
 * module header). */
export const WS = {
  listPersons: "health_o_mat/list_persons",
  panelData: "health_o_mat/panel_data",
  subscribe: "health_o_mat/subscribe",
  bookDrink: "health_o_mat/book_drink",
  undoLast: "health_o_mat/undo_last",
  saveMeasurement: "health_o_mat/save_measurement",
  setWellbeing: "health_o_mat/set_wellbeing",
  getUiSettings: "health_o_mat/get_ui_settings",
  setUiSettings: "health_o_mat/set_ui_settings",
  // Admin-only (server-gated; see "Admin surface" above).
  getSettings: "health_o_mat/get_settings",
  setSettings: "health_o_mat/set_settings",
  exportCsv: "health_o_mat/export_csv",
  startPersonFlow: "health_o_mat/start_person_flow",
  deletePerson: "health_o_mat/delete_person",
  backup: "health_o_mat/backup",
};

/* Feature areas per person (mirrors areas.py). A missing key means "enabled". */
export const AREA_KEYS = ["drink", "bp", "wellbeing"];

export const AREA_LABELS = {
  drink: "Trinken",
  bp: "Blutdruck",
  wellbeing: "Wohlbefinden",
};

/* Detail tabs, in fixed order; `area` links a tab to its feature toggle. */
export const TABS = [
  { key: "drink", label: "Trinken", area: "drink" },
  { key: "bp", label: "Blutdruck", area: "bp" },
  { key: "wellbeing", label: "Wohlbefinden", area: "wellbeing" },
];

/* Admin settings form. Structural limits mirror the backend schema so obvious
 * mistakes are caught before a round-trip; they are NOT a security boundary —
 * the server validates everything again. They are deliberately never STRICTER
 * than the server (ws_api.SETTINGS_SCHEMA), otherwise a value the server would
 * accept could not be saved. */
export const SETTINGS_LIMITS = {
  goalMin: 1,
  goalMax: 20000,
  resetMin: 0,
  resetMax: 23,
  // Both BP thresholds are validated as const.MIN_BP_VALUE..MAX_BP_VALUE
  // server-side (40..260) — one shared pair, intentionally.
  thresholdMin: 40,
  thresholdMax: 260,
  retentionMin: 0,
  retentionMax: 120,
  quickMlMin: 1,
  quickMlMax: 10000,
  maxQuickDrinks: 4,
  minQuickDrinks: 1,
};

/* Display fallbacks used ONLY when `get_settings` omits a key (the contract
 * lists every key, so this is a defensive default, not a data model). The
 * numbers mirror const.py (DEFAULT_DAILY_GOAL_ML, DEFAULT_SYS_THRESHOLD, …). */
export const SETTINGS_FALLBACKS = {
  daily_goal_ml: 2000,
  daily_reset_hour: 0,
  sys_threshold: 140,
  dia_threshold: 90,
  retention_months: 0,
  enable_sidebar_panel: false,
  quick_icon: "mdi:cup-water",
};

/* Export datasets (mirrors the `export_csv` service schema). */
export const EXPORT_DATASETS = [
  { value: "all", label: "Alles" },
  { value: "drinks", label: "Getränke" },
  { value: "blood_pressure", label: "Blutdruck" },
];

export const RING_RADIUS = 42;
export const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;
export const REFRESH_DEBOUNCE_MS = 150;

/* --- component CSS -------------------------------------------------------- */

export const PANEL_CSS = `
  :host {
    display: block; min-height: 100vh;
    background: var(--primary-background-color, #fafafa);
    color: var(--primary-text-color, #212121);
    -webkit-tap-highlight-color: transparent;
  }
  * { box-sizing: border-box; }
  .page { display: flex; flex-direction: column; min-height: 100vh; }

  .topbar {
    position: sticky; top: 0; z-index: 5;
    display: flex; align-items: center; gap: 8px; padding: 8px 12px;
    background: var(--app-header-background-color, var(--primary-color, #03a9f4));
    color: var(--app-header-text-color, var(--text-primary-color, #fff));
    box-shadow: 0 1px 4px rgba(0,0,0,.2);
  }
  .topbar .title { flex: 1; display: flex; align-items: center; gap: 8px;
    font-size: 1.05rem; font-weight: 600; min-width: 0; }
  .topbar .title .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .icon-btn {
    font: inherit; cursor: pointer; border: none; border-radius: 10px;
    background: rgba(255,255,255,.16); color: inherit;
    min-width: 44px; min-height: 44px; padding: 0 10px; font-size: 1.2rem;
    display: inline-flex; align-items: center; justify-content: center;
  }
  .icon-btn:active { transform: scale(.95); }
  .icon-btn[disabled] { opacity: .5; cursor: default; }

  .content { flex: 1; width: 100%; max-width: 1200px; margin: 0 auto; padding: 12px; }
  .footer {
    padding: 10px 12px 18px; text-align: center;
    font-size: .72rem; color: var(--secondary-text-color, #727272);
  }

  .grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
  @media (min-width: 600px) { .grid { grid-template-columns: repeat(2, 1fr); } }
  @media (min-width: 1000px) {
    .grid { grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
  }

  .tile {
    text-align: left; font: inherit; cursor: pointer;
    display: flex; flex-direction: column; gap: 10px; padding: 14px;
    border-radius: 16px;
    background: var(--card-background-color, var(--ha-card-background, #fff));
    color: var(--primary-text-color, #212121);
    border: 1px solid var(--divider-color, rgba(0,0,0,.08));
    box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.08));
    transition: box-shadow .12s ease, transform .12s ease;
  }
  .tile:hover { box-shadow: 0 3px 12px rgba(0,0,0,.16); }
  .tile:active { transform: scale(.99); }
  .tile:focus-visible { outline: 3px solid var(--primary-color, #03a9f4); outline-offset: 2px; }
  .tile.loading { cursor: default; opacity: .85; }
  .tile-head { display: flex; align-items: center; gap: 8px; }
  .tile-name { flex: 1; font-size: 1.05rem; font-weight: 600; min-width: 0;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tile-main { display: flex; align-items: center; gap: 14px; }
  .tile-stats { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .tile-ml { font-size: 1.15rem; font-weight: 700; }
  .tile-sub { font-size: .8rem; color: var(--secondary-text-color, #727272); }
  .tile-row { display: flex; align-items: center; gap: 8px; font-size: .92rem;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tile-row .em { font-size: 1.1rem; flex: none; }
  .tile-row .muted { color: var(--secondary-text-color, #727272); }

  .dot { width: 10px; height: 10px; border-radius: 50%;
    background: var(--primary-color, #03a9f4); flex: none; }

  .ring { position: relative; width: 132px; height: 132px; flex: none; }
  .ring.compact { width: 72px; height: 72px; }
  .ring svg { width: 100%; height: 100%; display: block; }
  .ring-track { fill: none; stroke: var(--divider-color, rgba(0,0,0,.12)); stroke-width: 8; }
  .ring-fill {
    fill: none; stroke: var(--primary-color, #03a9f4); stroke-width: 8; stroke-linecap: round;
    transition: stroke-dashoffset .45s ease;
  }
  .ring-fill.done { stroke: var(--success-color, #43a047); }
  .ring-label {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center; text-align: center; line-height: 1.12;
  }
  .ring-pct { font-weight: 700; font-size: 1.5rem; }
  .ring.compact .ring-pct { font-size: .95rem; }
  .ring-sub { font-size: .72rem; color: var(--secondary-text-color, #727272); margin-top: 2px; }

  .card {
    background: var(--card-background-color, var(--ha-card-background, #fff));
    border: 1px solid var(--divider-color, rgba(0,0,0,.08));
    border-radius: 16px; padding: 14px;
    display: flex; flex-direction: column; gap: 12px;
  }

  .btn {
    font: inherit; cursor: pointer; border: none; border-radius: 12px;
    padding: 12px 14px; min-height: 48px;
    background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff);
    font-weight: 600; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    touch-action: manipulation; transition: filter .15s ease, transform .1s ease;
  }
  .btn:hover { filter: brightness(1.06); }
  .btn:active { transform: scale(.98); }
  .btn:focus-visible { outline: 3px solid var(--primary-color, #03a9f4); outline-offset: 2px; }
  .btn[disabled] { opacity: .55; cursor: default; filter: none; }
  .btn.ghost { background: transparent; color: var(--primary-color, #03a9f4);
    border: 1px solid var(--primary-color, #03a9f4); }

  .quick { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
  @media (min-width: 600px) { .quick { grid-template-columns: repeat(4, 1fr); } }
  .quick .btn { flex-direction: column; min-height: 66px; }
  .quick .btn .ml { font-size: .75rem; font-weight: 400; opacity: .9; }

  .freetext { display: flex; gap: 8px; }
  .freetext input {
    flex: 1; min-width: 0; min-height: 48px; padding: 10px 12px; font: inherit;
    border-radius: 12px; border: 1px solid var(--divider-color, rgba(0,0,0,.2));
    background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121);
  }
  .freetext .btn { flex: none; }

  .tabs { display: flex; gap: 4px; background: var(--secondary-background-color, rgba(0,0,0,.04));
    padding: 4px; border-radius: 12px; }
  .tab { flex: 1; cursor: pointer; border: none; background: transparent; font: inherit;
    color: var(--primary-text-color, #212121); font-weight: 600; padding: 10px 6px;
    min-height: 44px; border-radius: 9px; }
  .tab.active { background: var(--card-background-color, #fff);
    box-shadow: 0 1px 2px rgba(0,0,0,.15); color: var(--primary-color, #03a9f4); }
  .tab:focus-visible { outline: 3px solid var(--primary-color, #03a9f4); outline-offset: 2px; }

  .person-head { display: flex; align-items: center; gap: 10px; margin: 2px 0 12px;
    font-size: 1.15rem; font-weight: 600; }
  .views { display: flex; flex-direction: column; gap: 12px; }

  .kv { display: flex; justify-content: space-between; gap: 12px; font-size: .95rem; }
  .kv .k { color: var(--secondary-text-color, #727272); }
  .kv .v { font-weight: 600; text-align: right; }

  .status { display: inline-flex; align-items: center; gap: 6px; font-size: .85rem;
    padding: 4px 10px; border-radius: 999px; font-weight: 600; }
  .status.good { color: var(--success-color, #43a047); background: rgba(67,160,71,.14); }
  .status.ok { color: var(--primary-color, #03a9f4); background: rgba(3,169,244,.14); }
  .status.warn { color: var(--warning-color, #ff9800); background: rgba(255,152,0,.16); }
  .status.bad { color: var(--error-color, #db4437); background: rgba(219,68,55,.14); }

  .banner { display: flex; align-items: center; gap: 10px; padding: 10px 12px;
    border-radius: 12px; font-size: .9rem;
    background: var(--secondary-background-color, rgba(0,0,0,.04));
    border-left: 4px solid var(--error-color, #db4437);
    color: var(--error-color, #db4437); font-weight: 600; }
  .banner.info { border-left-color: var(--primary-color, #03a9f4);
    color: var(--primary-text-color, #212121); font-weight: 500; }

  .msg { padding: 14px; border-radius: 12px;
    background: var(--secondary-background-color, rgba(0,0,0,.04));
    color: var(--secondary-text-color, #727272); }
  .msg.error { color: var(--error-color, #db4437); }
  .msg .btn { margin-top: 12px; }

  .bd-row { display: grid; grid-template-columns: 84px 1fr auto; gap: 8px;
    align-items: center; font-size: .88rem; }
  .bd-track { height: 10px; border-radius: 6px; overflow: hidden;
    background: var(--divider-color, rgba(0,0,0,.1)); }
  .bd-fill { height: 100%; background: var(--primary-color, #03a9f4); }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { padding: 5px 10px; border-radius: 999px; font-size: .82rem;
    background: var(--secondary-background-color, rgba(0,0,0,.05)); }

  .bp-head { display: flex; flex-direction: column; gap: 4px; }
  .bp-big { font-size: 2.5rem; font-weight: 700; line-height: 1; }
  .bp-meta { font-size: .9rem; color: var(--secondary-text-color, #727272);
    display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .bp-inputs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .field { display: flex; flex-direction: column; gap: 4px; font-size: .8rem;
    color: var(--secondary-text-color, #727272); min-width: 0; }
  .field input, .field select, .field textarea {
    width: 100%; min-height: 48px; padding: 8px 10px; font: inherit;
    border-radius: 10px; border: 1px solid var(--divider-color, rgba(0,0,0,.2));
    background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121);
  }
  .spark { display: flex; align-items: flex-end; gap: 4px; height: 72px; padding-top: 4px; }
  .spark .bar { flex: 1; min-width: 5px; border-radius: 4px 4px 0 0;
    background: var(--primary-color, #03a9f4); }

  .wb-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
  .wb-btn {
    font: inherit; cursor: pointer; min-height: 86px; padding: 8px 2px;
    border-radius: 14px; border: 1px solid var(--divider-color, rgba(0,0,0,.12));
    background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121);
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px;
  }
  .wb-btn:active { transform: scale(.97); }
  .wb-btn:focus-visible { outline: 3px solid var(--primary-color, #03a9f4); outline-offset: 2px; }
  .wb-btn .emoji { font-size: 1.9rem; line-height: 1; }
  .wb-btn .lbl { font-size: .72rem; color: var(--secondary-text-color, #727272); text-align: center; }
  .wb-btn.active { border-color: var(--primary-color, #03a9f4);
    background: var(--secondary-background-color, rgba(3,169,244,.1)); }
  @media (max-width: 400px) { .wb-btn .lbl { display: none; } }

  .wb-history { display: flex; flex-wrap: wrap; gap: 8px; }
  .wb-hist { display: flex; flex-direction: column; align-items: center; gap: 2px;
    font-size: .68rem; color: var(--secondary-text-color, #727272); min-width: 40px; }
  .wb-hist .emoji { font-size: 1.3rem; line-height: 1; }

  /* --- Wohlbefinden-Score-Chart (REQ-HOM-112) ---------------------------- */
  .wb-chart { width: 100%; }
  .wb-chart svg { width: 100%; height: auto; display: block; }
  .wb-chart .grid-line { stroke: var(--divider-color, rgba(0,0,0,.12)); stroke-width: 1; }
  .wb-chart .axis-text { fill: var(--secondary-text-color, #727272); font-size: 11px; }
  .wb-chart .axis-extreme { fill: var(--primary-text-color, #212121); font-weight: 700; }
  .wb-chart .area { fill: var(--primary-color, #03a9f4); opacity: .12; }
  .wb-chart .line { fill: none; stroke: var(--primary-color, #03a9f4); stroke-width: 2.5;
    stroke-linecap: round; stroke-linejoin: round; }
  .wb-chart .point { fill: var(--card-background-color, #fff);
    stroke: var(--primary-color, #03a9f4); stroke-width: 2; }
  .wb-chart .point-current { fill: var(--primary-color, #03a9f4);
    stroke: var(--card-background-color, #fff); stroke-width: 2.5; }

  .muted { color: var(--secondary-text-color, #727272); font-size: .85rem; }

  /* --- Admin/Settings (L3, concept 4.5 / §8.4) --------------------------- */
  .settings-form { display: flex; flex-direction: column; gap: 12px; }
  .settings-grid { display: grid; grid-template-columns: 1fr; gap: 10px; }
  @media (min-width: 600px) { .settings-grid { grid-template-columns: repeat(2, 1fr); } }
  .hint { font-size: .75rem; color: var(--secondary-text-color, #727272); line-height: 1.35; }
  .field code, .settings-form code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: .8rem;
  }
  .field textarea {
    min-height: 190px; resize: vertical; line-height: 1.45;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: .85rem;
  }
  .qd-list { display: flex; flex-direction: column; gap: 10px; }
  .qd-slot {
    display: grid; grid-template-columns: 1fr; gap: 8px; padding: 10px;
    border-radius: 12px; border: 1px solid var(--divider-color, rgba(0,0,0,.12));
    background: var(--secondary-background-color, rgba(0,0,0,.02));
  }
  @media (min-width: 700px) {
    .qd-slot { grid-template-columns: 2fr 1fr 2fr auto; align-items: end; }
  }
  .qd-slot .btn { min-height: 44px; min-width: 44px; padding: 10px 12px; }
  .check { display: flex; align-items: center; gap: 10px; font-size: .95rem; min-height: 48px; }
  .check input { width: 22px; height: 22px; flex: none; }
  .export-row { display: grid; grid-template-columns: 1fr; gap: 10px; }
  @media (min-width: 600px) { .export-row { grid-template-columns: 1fr auto; align-items: end; } }
  .settings-status { border-radius: 12px; padding: 10px 12px; font-size: .9rem; font-weight: 600; }
  .settings-status.ok { color: var(--success-color, #43a047); background: rgba(67,160,71,.14); }
  .settings-status.err { color: var(--error-color, #db4437); background: rgba(219,68,55,.14); }
  .settings-actions { display: flex; flex-wrap: wrap; gap: 10px; }
  .settings-actions .btn { flex: 1 1 190px; }
  .card-title { font-weight: 600; font-size: .95rem; }

  /* --- Person management (D7) -------------------------------------------- */
  .person-list { display: flex; flex-direction: column; gap: 10px; }
  .person-manage {
    display: flex; flex-direction: column; gap: 8px; padding: 10px;
    border-radius: 12px; border: 1px solid var(--divider-color, rgba(0,0,0,.12));
    background: var(--secondary-background-color, rgba(0,0,0,.02));
  }
  .person-manage .kv { align-items: center; }
`;

/* --- pure helpers --------------------------------------------------------- */

export function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function toNumber(value, fallback) {
  const n = typeof value === "number" ? value : parseFloat(value);
  return Number.isFinite(n) ? n : fallback;
}

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function errMsg(err) {
  if (err == null) return "Unbekannter Fehler.";
  if (typeof err === "string") return err;
  if (err.message) return String(err.message);
  if (err.body && err.body.message) return String(err.body.message);
  try {
    return JSON.stringify(err);
  } catch (_e) {
    return String(err);
  }
}

/* Integer from a form field: "" / garbage -> null, "3,5" -> 4 (rounded). */
export function intOrNull(raw) {
  if (raw == null) return null;
  const s = String(raw).trim().replace(",", ".");
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? Math.round(n) : null;
}

/* WS error -> display text. Home Assistant rejects `callWS` with an object that
 * carries `code`/`message` and (for validated commands) `translation_placeholders`
 * — the backend puts the offending lexicon line there, so it is appended instead
 * of being swallowed by `errMsg`. */
export function wsErrorText(err) {
  const base = errMsg(err);
  const ph = err && err.translation_placeholders;
  if (ph && typeof ph === "object") {
    if (ph.detail) return `${base}: ${String(ph.detail)}`;
    const parts = Object.keys(ph)
      .filter((k) => ph[k] != null && ph[k] !== "")
      .map((k) => `${k}=${ph[k]}`);
    if (parts.length) return `${base} (${parts.join(", ")})`;
  }
  return base;
}

/* Normalised quick-drink list, used for both dirty-checking and payloads. */
export function normalizeQuickDrinks(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .slice(0, SETTINGS_LIMITS.maxQuickDrinks)
    .filter((d) => d && typeof d === "object")
    .map((d) => ({
      key: d.key == null ? "" : String(d.key),
      label: String(d.label == null ? "" : d.label).trim(),
      ml: toNumber(d.ml, 0),
      icon: String(d.icon == null ? "" : d.icon),
    }));
}

/* Attribute-safe string (never prints "null"/"undefined" into `value=`). */
export function attrValue(value) {
  return value === null || value === undefined ? "" : escapeHtml(String(value));
}

export function datasetLabel(value) {
  const hit = EXPORT_DATASETS.find((d) => d.value === value);
  return hit ? hit.label : String(value == null ? "" : value);
}

export function relativeTime(iso) {
  const ts = Date.parse(iso);
  if (!Number.isFinite(ts)) return "";
  const diff = Date.now() - ts;
  if (diff < 60000) return "gerade eben";
  const min = Math.round(diff / 60000);
  if (min < 60) return `vor ${min} min`;
  const hours = Math.round(min / 60);
  if (hours < 24) return `vor ${hours} h`;
  const days = Math.round(hours / 24);
  return `vor ${days} d`;
}

export function fmtMl(value) {
  const n = toNumber(value, 0);
  return `${Math.round(n)} ml`;
}

/* Feature-area normalisation: a missing `areas` object OR a missing key means
 * "enabled" — only an explicit `false` hides an area (mirrors areas.py). */
export function normalizeAreas(raw) {
  const out = { drink: true, bp: true, wellbeing: true };
  if (raw && typeof raw === "object") {
    AREA_KEYS.forEach((key) => {
      if (Object.prototype.hasOwnProperty.call(raw, key)) out[key] = raw[key] !== false;
    });
  }
  return out;
}

/* Areas for one person: prefer the live panel_data block, fall back to the
 * list_persons entry, then to "all enabled". */
export function areasForPerson(person, data) {
  if (data && data.areas && typeof data.areas === "object") return normalizeAreas(data.areas);
  if (person && person.areas && typeof person.areas === "object") {
    return normalizeAreas(person.areas);
  }
  return normalizeAreas(null);
}

/* Tabs whose area is enabled, preserving the fixed TABS order. */
export function enabledTabs(areas) {
  const a = normalizeAreas(areas);
  return TABS.filter((tab) => a[tab.area]);
}

/* Stable page key for a person: the slug (`entry.data["person"]`) — NEVER the
 * display name. Falls back to the entry_id when a slug is missing. */
export function personSlug(person) {
  const slug = person && person.person_slug ? String(person.person_slug) : "";
  if (slug) return slug;
  return person && person.entry_id ? String(person.entry_id) : "";
}

/* Resolve a deep-link value: slug first, then entry_id. Unknown -> null. */
export function resolvePersonByParam(persons, value) {
  const wanted = value == null ? "" : String(value);
  if (!wanted) return null;
  const list = Array.isArray(persons) ? persons : [];
  return (
    list.find((p) => p && p.person_slug && String(p.person_slug) === wanted) ||
    list.find((p) => p && String(p.entry_id) === wanted) ||
    null
  );
}

export function normalizePersons(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((p) => p && p.entry_id)
    .map((p) => ({
      entry_id: String(p.entry_id),
      display_name: p.display_name ? String(p.display_name) : String(p.entry_id),
      device_id: p.device_id || null,
      person_slug: p.person_slug == null ? "" : String(p.person_slug),
      areas: normalizeAreas(p.areas),
    }));
}

/* Free-text drink entry: "Kaffee 300ml" -> { ml: 300, type: "Kaffee" }. */
export function parseDrinkText(text) {
  const raw = String(text == null ? "" : text).trim();
  if (!raw) return null;
  const match = raw.match(/(\d+(?:[.,]\d+)?)\s*(ml|milliliter|l|liter|cl)?/i);
  if (!match) return null;
  let amount = parseFloat(match[1].replace(",", "."));
  const unit = (match[2] || "ml").toLowerCase();
  if (unit === "l" || unit === "liter") amount *= 1000;
  else if (unit === "cl") amount *= 10;
  if (!Number.isFinite(amount) || amount <= 0 || amount > 10000) return null;
  const before = raw.slice(0, match.index).trim();
  const after = raw.slice(match.index + match[0].length).trim();
  const type = `${before} ${after}`.trim();
  return { ml: Math.round(amount), type: type.slice(0, 60) };
}

export function ringHtml(percent, opts) {
  const options = opts || {};
  const pct = toNumber(percent, 0);
  const fill = clamp(pct, 0, 100);
  const offset = RING_CIRCUMFERENCE * (1 - fill / 100);
  const done = pct >= 100 ? " done" : "";
  const cls = options.compact ? "ring compact" : "ring";
  const sub = options.sub
    ? `<span class="ring-sub">${escapeHtml(options.sub)}</span>`
    : "";
  return `<div class="${cls}">
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle class="ring-track" cx="50" cy="50" r="${RING_RADIUS}"></circle>
        <circle class="ring-fill${done}" cx="50" cy="50" r="${RING_RADIUS}"
          stroke-dasharray="${RING_CIRCUMFERENCE.toFixed(2)}"
          stroke-dashoffset="${offset.toFixed(2)}"
          transform="rotate(-90 50 50)"></circle>
      </svg>
      <div class="ring-label">
        <span class="ring-pct">${Math.round(pct)}%</span>${sub}
      </div>
    </div>`;
}

export function categoryInfo(key) {
  const k = String(key == null ? "" : key).toLowerCase();
  return BP_CATEGORIES[k] || null;
}

/* --- Wohlbefinden-Score-Chart (REQ-HOM-112) -------------------------------- */

/* Score-Skala: 1 = schlechtester … N = bester Wert. Die Länge folgt der
 * Zustandsliste (heute 5 Stufen) — eine neue Stufe schlägt automatisch
 * durch (spiegelt logic.wellbeing_score / const.WELLBEING_STATES). */
export const WELLBEING_SCORE_MIN = 1;
export const WELLBEING_SCORE_MAX = WELLBEING_STATES.length;

/* Chart-Geometrie in ViewBox-Einheiten; das SVG skaliert über `width:100%`
 * (mobil, ohne horizontale Scrollbars, ohne feste Pixelbreiten). */
const CHART_W = 320;
const CHART_H = 180;
const CHART_PAD = { top: 14, right: 14, bottom: 26, left: 26 };

function pad2(value) {
  return String(value).padStart(2, "0");
}

/* "19.10." — kompakte Achsenbeschriftung (mobil lesbar). */
export function formatChartDate(ts) {
  if (ts == null || !Number.isFinite(ts)) return "";
  const date = new Date(ts);
  if (!Number.isFinite(date.getTime())) return "";
  return `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)}.`;
}

/* "19.10.2026, 14:30 Uhr" — Zeitpunkt für die Tooltips. */
export function formatChartDateTime(ts) {
  if (ts == null || !Number.isFinite(ts)) return "";
  const date = new Date(ts);
  if (!Number.isFinite(date.getTime())) return "";
  const day = `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)}.${date.getFullYear()}`;
  return `${day}, ${pad2(date.getHours())}:${pad2(date.getMinutes())} Uhr`;
}

/* Score eines Eintrags — DER SERVER IST DIE WAHRHEIT (REQ-HOM-112).
 *
 * 1. Ist das Feld `score` im Objekt vorhanden (auch bei `null`), gilt der
 *    Server-Wert: `score` verwenden; ist er `null` oder nicht numerisch,
 *    gibt es KEINEN Score (null). Eine clientseitige Ersatzableitung waere
 *    eine zweite Wahrheit — der Server liefert bewusst `null`, wenn der
 *    Zustand nicht auf der kanonischen Skala liegt.
 * 2. FEHLT das Feld `score` komplett (aelterer Server, der das Feld noch
 *    nicht kennt), wird der Score clientseitig aus dem kanonischen Key
 *    abgeleitet — EXAKT (case-sensitiv), wie `logic.wellbeing_score`:
 *    Index + 1 in aufsteigender Qualitaet. Unbekannter Key -> null.
 * 3. Der Score muss im Bereich 1..N liegen; alles andere -> null.
 */
export function wellbeingScore(raw) {
  if (!raw || typeof raw !== "object") return null;
  if ("score" in raw) {
    const direct = toNumber(raw.score, NaN);
    if (!Number.isFinite(direct)) return null;
    const rounded = Math.round(direct);
    if (rounded >= WELLBEING_SCORE_MIN && rounded <= WELLBEING_SCORE_MAX) return rounded;
    return null;
  }
  const key = typeof raw.key === "string" ? raw.key : "";
  const index = WELLBEING_STATES.findIndex((state) => state.key === key);
  return index >= 0 ? index + 1 : null;
}

/* Verlauf -> verwertbare Punkte. Einträge ohne verwertbaren Score (kein
 * `score` und kein bekannter `key`) werden übersprungen; kein Array ->
 * leere Liste (nie ein Absturz, keine NaN-Koordinaten). */
export function wellbeingScorePoints(history) {
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
      emoji: String(entry.emoji == null ? "" : entry.emoji),
      ts: Number.isFinite(parsed) ? parsed : null,
    });
  });
  return points;
}

/* Serie des Score-Verlaufs: Historienpunkte + der AKTUELLE Wert als letzter
 * Punkt.
 *
 * Historie-Semantik (store.set_wellbeing): ein Historieneintrag `{ts, status}`
 * bedeutet "bis zu diesem Zeitpunkt galt `status`" — der aktuelle Zustand steht
 * ausschließlich in `wellbeing` (`status`/`ts`, im WS-Payload `key`/`at`).
 * Der letzte Historienpunkt ist damit der ABGELÖSTE Wert; ohne den aktuellen
 * Punkt würde der Chart den alten Wert als "aktuell" markieren (Kopfzeile und
 * Chart widersprächen sich sichtbar).
 *
 * `current` = {key, label, emoji, score, at}. Der Score folgt der Regel von
 * `wellbeingScore`: vorhandenes `current.score` ist die Wahrheit (der Server
 * liefert `null`, wenn es keinen Score gibt — dann gibt es auch keinen
 * aktuellen Punkt); nur wenn das Feld FEHLT, wird er aus `current.key`
 * abgeleitet (ältere Payloads ohne `score`). Ohne verwertbaren Score bleibt
 * die Serie = Historie.
 *
 * MARKER (der aktuelle Punkt wird EXPLICIT markiert): nur der angehängte
 * aktuelle Punkt trägt `isCurrent: true`; die Historienpunkte tragen das
 * Feld NICHT. Der Chart hebt deshalb genau den Punkt hervor, der den
 * aktuellen Wert darstellt. Ohne aktuellen Wert wird KEIN Punkt
 * hervorgehoben — der letzte Punkt der Serie ist dann ein ABGELÖSTER
 * Historienwert (der Chart behauptet in dem Fall "letzter Wert", nicht
 * "aktuell"; die Kopfzeile zeigt dann ebenfalls keinen Score).
 */
export function wellbeingSeries(history, current) {
  const points = wellbeingScorePoints(history);
  const score = wellbeingScore(current);
  if (score == null) return points;
  const rawTs = current && current.at != null ? String(current.at) : "";
  const parsed = rawTs ? Date.parse(rawTs) : NaN;
  const ts = Number.isFinite(parsed) ? parsed : null;
  const last = points.length ? points[points.length - 1] : null;
  /* Duplikat vermeiden: gleicher Zeitstempel UND gleicher Score -> der
   * aktuelle Wert ist im Verlauf bereits abgebildet (kein doppelter Punkt).
   * Dieser Punkt IST dann der aktuelle Wert -> er wird (und nur er) als
   * `isCurrent` markiert. */
  if (last && last.ts === ts && last.score === score) {
    last.isCurrent = true;
    return points;
  }
  points.push({
    score,
    label: String(current.label == null ? "" : current.label),
    emoji: String(current.emoji == null ? "" : current.emoji),
    ts,
    /* NUR der angehaengte aktuelle Punkt traegt den Marker — die
     * Historienpunkte sind abgeloeste Werte. */
    isCurrent: true,
  });
  return points;
}

/* X-Positionen (0..1): zeitbasiert, wenn ALLE Punkte einen Zeitstempel
 * tragen; sonst indexbasiert (gleichmäßig verteilt). */
function chartPositions(points) {
  const count = points.length;
  if (!count) return [];
  if (count === 1) return [0.5];
  const stamps = points.map((point) => point.ts);
  if (stamps.every((value) => value != null)) {
    let min = stamps[0];
    let max = stamps[0];
    stamps.forEach((value) => {
      if (value < min) min = value;
      if (value > max) max = value;
    });
    const span = max - min;
    return stamps.map((value) => (span > 0 ? (value - min) / span : 0.5));
  }
  return points.map((_, index) => index / (count - 1));
}

/* SVG-Linienchart des Score-Verlaufs (Zeit auf X, Score auf Y).
 *
 * Invariante: der aktuelle Wert ist der Punkt mit `isCurrent === true` (siehe
 * `wellbeingSeries` — dort wird er angehängt und markiert). NUR dieser Punkt
 * trägt `point-current` (und den groesseren Radius); die aria-label nennt
 * seinen Score als "aktuell". Gibt es keinen aktuellen Wert, wird KEIN Punkt
 * hervorgehoben und die aria-label nennt den letzten Serienpunkt als
 * "letzter Wert" — der letzte Punkt ist dann ein abgeloester Historienwert
 * und darf nicht als "aktuell" behauptet werden (die Kopfzeile zeigt in
 * dem Fall ebenfalls keinen Score). */
export function wellbeingChartSvg(points) {
  const list = Array.isArray(points) ? points : [];
  if (!list.length) return "";
  const plotW = CHART_W - CHART_PAD.left - CHART_PAD.right;
  const plotH = CHART_H - CHART_PAD.top - CHART_PAD.bottom;
  const span = Math.max(1, WELLBEING_SCORE_MAX - WELLBEING_SCORE_MIN);
  const positions = chartPositions(list);
  const coords = list.map((point, index) => ({
    x: CHART_PAD.left + positions[index] * plotW,
    y: CHART_PAD.top + ((WELLBEING_SCORE_MAX - point.score) / span) * plotH,
  }));

  /* Gridlines + Y-Beschriftung je Stufe; die Extremwerte 1 und 5 sind
   * hervorgehoben (die Skala 1…5 muss sichtbar transportiert werden). */
  const grid = [];
  for (let score = WELLBEING_SCORE_MIN; score <= WELLBEING_SCORE_MAX; score += 1) {
    const y = CHART_PAD.top + ((WELLBEING_SCORE_MAX - score) / span) * plotH;
    const extreme = score === WELLBEING_SCORE_MIN || score === WELLBEING_SCORE_MAX;
    grid.push(
      `<line class="grid-line" x1="${CHART_PAD.left}" y1="${y.toFixed(1)}" x2="${(CHART_W - CHART_PAD.right).toFixed(1)}" y2="${y.toFixed(1)}"></line>`,
      `<text class="axis-text${extreme ? " axis-extreme" : ""}" x="${CHART_PAD.left - 6}" y="${(y + 4).toFixed(1)}" text-anchor="end">${score}</text>`
    );
  }

  /* Kurve + optionale Fläche. */
  const linePath = coords
    .map((coord, index) => `${index === 0 ? "M" : "L"}${coord.x.toFixed(1)} ${coord.y.toFixed(1)}`)
    .join(" ");
  const baseY = CHART_PAD.top + plotH;
  const areaPath =
    coords.length >= 2
      ? `M${coords[0].x.toFixed(1)} ${baseY.toFixed(1)} ` +
        coords.map((coord) => `L${coord.x.toFixed(1)} ${coord.y.toFixed(1)}`).join(" ") +
        ` L${coords[coords.length - 1].x.toFixed(1)} ${baseY.toFixed(1)} Z`
      : "";

  /* Datenpunkte mit Tooltip (Zeitpunkt + Label + Score); nur der explizit
   * markierte aktuelle Wert (`isCurrent`) ist hervorgehoben — der letzte
   * Punkt der Serie ist ohne aktuellen Wert ein abgeloester Historienwert. */
  const dots = list.map((point, index) => {
    const coord = coords[index];
    const current = point.isCurrent === true;
    const when = point.ts != null ? formatChartDateTime(point.ts) : "ohne Zeitangabe";
    const label = point.label || "Wohlbefinden";
    const title = `${when} \u2013 ${label} (${point.score} / ${WELLBEING_SCORE_MAX})`;
    const cls = current ? "point point-current" : "point";
    const radius = current ? 5 : 3.2;
    return `<circle class="${cls}" cx="${coord.x.toFixed(1)}" cy="${coord.y.toFixed(1)}" r="${radius}"><title>${escapeHtml(title)}</title></circle>`;
  });

  /* X-Achse: erstes und letztes Datum (mobil lesbar). */
  const firstDate = formatChartDate(list[0].ts);
  const lastDate = formatChartDate(list[list.length - 1].ts);
  const xLabels = [];
  if (firstDate) {
    xLabels.push(
      `<text class="axis-text" x="${CHART_PAD.left}" y="${CHART_H - 8}" text-anchor="start">${escapeHtml(firstDate)}</text>`
    );
  }
  if (lastDate && lastDate !== firstDate) {
    xLabels.push(
      `<text class="axis-text" x="${CHART_W - CHART_PAD.right}" y="${CHART_H - 8}" text-anchor="end">${escapeHtml(lastDate)}</text>`
    );
  }

  const last = list[list.length - 1];
  /* Der aktuelle Punkt ist explizit markiert (`isCurrent`). Ohne ihn ist der
   * letzte Punkt ein abgeloester Historienwert — die Aussage lautet dann
   * "letzter Wert" statt "aktuell" (sonst widersprueche der Chart der
   * Kopfzeile, die in dem Fall keinen Score zeigt). */
  const currentPoint = list.find((point) => point && point.isCurrent === true) || null;
  const summary = currentPoint
    ? `Wohlbefinden-Score-Verlauf: ${list.length} Meldung${list.length === 1 ? "" : "en"}, ` +
      `aktuell ${currentPoint.score} von ${WELLBEING_SCORE_MAX}${currentPoint.label ? ` (${currentPoint.label})` : ""}`
    : `Wohlbefinden-Score-Verlauf: ${list.length} Meldung${list.length === 1 ? "" : "en"}, ` +
      `letzter Wert ${last.score} von ${WELLBEING_SCORE_MAX}${last.label ? ` (${last.label})` : ""}`;

  return `<svg viewBox="0 0 ${CHART_W} ${CHART_H}" role="img" aria-label="${escapeHtml(summary)}" preserveAspectRatio="xMidYMid meet">${grid.join("")}${areaPath ? `<path class="area" d="${areaPath}"></path>` : ""}${coords.length >= 2 ? `<path class="line" d="${linePath}"></path>` : ""}${dots.join("")}${xLabels.join("")}</svg>`;
}

/* Chart-Card für den Tab "Wohlbefinden".
 *
 * `opts.current` = aktueller Wohlbefinden-Block ({key, label, emoji, score,
 * at}); er wird als letzter Punkt an die Serie gehängt (siehe
 * `wellbeingSeries`), damit `point-current` und die aria-label den AKTUELLEN
 * Wert nennen und nicht den zuletzt abgelösten Historienpunkt. Ohne
 * `opts.current` (bzw. ohne verwertbaren Score) bleibt die Serie = Historie:
 * dann wird kein Punkt hervorgehoben und die aria-label nennt den letzten
 * Wert ("letzter Wert"), passend zur Kopfzeile ohne Score.
 *
 * Ohne verwertbare Punkte wird ein verständlicher Hinweis statt eines leeren
 * Charts gezeigt. */
export function wellbeingChartHtml(history, opts) {
  const options = opts || {};
  const title = options.title ? String(options.title) : "Score-Verlauf";
  const head = `<div class="card-title">${escapeHtml(title)}</div>`;
  const points = wellbeingSeries(history, options.current);
  if (!points.length) {
    const empty = options.emptyText
      ? String(options.emptyText)
      : "Noch keine Wohlbefinden-Meldung \u2013 der Verlauf erscheint nach der ersten Meldung.";
    return `<div class="card">${head}${messageHtml(empty, false)}</div>`;
  }
  const worst = WELLBEING_STATES[0] ? WELLBEING_STATES[0].label : "schlecht";
  const bestState = WELLBEING_STATES[WELLBEING_STATES.length - 1];
  const best = bestState ? bestState.label : "gut";
  const hint = `${WELLBEING_SCORE_MIN} = ${worst} \u00B7 ${WELLBEING_SCORE_MAX} = ${best}`;
  return `<div class="card">${head}<div class="wb-chart">${wellbeingChartSvg(points)}</div><div class="hint">${escapeHtml(hint)}</div></div>`;
}

/* Empty-state message block, shared by every view. */
export function messageHtml(text, isError) {
  const retry = isError
    ? `<button class="btn ghost" data-action="retry" type="button">Erneut versuchen</button>`
    : "";
  return `<div class="msg${isError ? " error" : ""}">${escapeHtml(text)}${retry}</div>`;
}

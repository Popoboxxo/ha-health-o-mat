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

/* Empty-state message block, shared by every view. */
export function messageHtml(text, isError) {
  const retry = isError
    ? `<button class="btn ghost" data-action="retry" type="button">Erneut versuchen</button>`
    : "";
  return `<div class="msg${isError ? " error" : ""}">${escapeHtml(text)}${retry}</div>`;
}

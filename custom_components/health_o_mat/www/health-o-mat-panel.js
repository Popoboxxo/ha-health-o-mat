/**
 * Health-O-Mat — Sidebar Panel (L2).
 *
 * Vanilla Web Component, no build toolchain, no external imports.
 * Self-contained ES2020, delivered bundled by the integration (see panel.py)
 * and registered via `panel_custom.async_register_panel(webcomponent_name=...)`.
 *
 * DOM API set by Home Assistant for `panel_custom` web components:
 *   set hass(hass)     — the Home Assistant object (states, callWS, connection)
 *   set panel(panel)   — panel descriptor; optional `panel.config` may carry
 *                        { entry_id } or { person } to pin an initial person
 *
 * Data flow (no polling, no own timer):
 *   - first `hass` set  -> bootstrap: ui settings + list_persons + panel_data
 *   - `health_o_mat/subscribe` events -> reload the affected person(s)
 *   - every `hass` set  -> read LIVE values from hass.states[entity_id]
 *   - entity ids are NEVER guessed; they come from the WS `entities` block
 *     (resolved server-side via the stable `{entry_id}_{suffix}` unique_id)
 *
 * Views:
 *   - overview: responsive grid, one tile per person (L2 start)
 *   - detail:   tabs Trinken | Blutdruck | Wohlbefinden (concept 4.2–4.4)
 *
 * Robustness: missing entities/states, per-person load errors, and WS write
 * errors are surfaced without ever breaking the panel.
 */

const PANEL_TAG = "health-o-mat-panel";
const PANEL_VERSION = "0.1.0";

/* Quick drinks for the "Trinken" tab. `type` is the canonical drink label
 * stored on the drink (`store.add_drink`), used for the caffeine breakdown. */
const QUICK_DRINKS = [
  { label: "Glas Wasser", ml: 200, emoji: "\u{1F4A7}", type: "Wasser" },
  { label: "Flasche", ml: 500, emoji: "\u{1F376}", type: "Wasser" },
  { label: "Kaffee", ml: 250, emoji: "\u2615", type: "Kaffee" },
  { label: "Saft", ml: 200, emoji: "\u{1F964}", type: "Saft" },
];

/* Wellbeing taps (mirrors const.WELLBEING_STATES). */
const WELLBEING_STATES = [
  { key: "very_bad", label: "Sehr schlecht", emoji: "\u{1F635}" },
  { key: "bad", label: "Schlecht", emoji: "\u{1F641}" },
  { key: "okay", label: "Okay", emoji: "\u{1F610}" },
  { key: "good", label: "Gut", emoji: "\u{1F642}" },
  { key: "great", label: "Super", emoji: "\u{1F604}" },
];

/* WHO blood-pressure category keys (logic.bp_category) -> label + colour. */
const BP_CATEGORIES = {
  optimal: { label: "Optimal", cls: "good" },
  normal: { label: "Normal", cls: "good" },
  high_normal: { label: "Hochnormal", cls: "ok" },
  grade_1: { label: "Hypertonie Grad 1", cls: "warn" },
  grade_2: { label: "Hypertonie Grad 2", cls: "warn" },
  grade_3: { label: "Hypertonie Grad 3", cls: "bad" },
  crisis: { label: "Krise", cls: "bad" },
};

/* Pace labels (ws_api.compute_pace). */
const PACE_INFO = {
  goal_reached: { text: "Tagesziel erreicht", cls: "good" },
  ahead: { text: "Auf Kurs (voraus)", cls: "good" },
  on_track: { text: "Auf Kurs", cls: "ok" },
  behind: { text: "Zu langsam", cls: "warn" },
};

const WS = {
  listPersons: "health_o_mat/list_persons",
  panelData: "health_o_mat/panel_data",
  subscribe: "health_o_mat/subscribe",
  bookDrink: "health_o_mat/book_drink",
  undoLast: "health_o_mat/undo_last",
  saveMeasurement: "health_o_mat/save_measurement",
  setWellbeing: "health_o_mat/set_wellbeing",
  getUiSettings: "health_o_mat/get_ui_settings",
  setUiSettings: "health_o_mat/set_ui_settings",
};

const RING_RADIUS = 42;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;
const REFRESH_DEBOUNCE_MS = 150;

const PANEL_CSS = `
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
  .field input {
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
`;

/* --- pure helpers --------------------------------------------------------- */

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

function errMsg(err) {
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

function relativeTime(iso) {
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

function fmtMl(value) {
  const n = toNumber(value, 0);
  return `${Math.round(n)} ml`;
}

function normalizePersons(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((p) => p && p.entry_id)
    .map((p) => ({
      entry_id: String(p.entry_id),
      display_name: p.display_name ? String(p.display_name) : String(p.entry_id),
      device_id: p.device_id || null,
    }));
}

/* Free-text drink entry: "Kaffee 300ml" -> { ml: 300, type: "Kaffee" }. */
function parseDrinkText(text) {
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

function ringHtml(percent, opts) {
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

function categoryInfo(key) {
  const k = String(key == null ? "" : key).toLowerCase();
  return BP_CATEGORIES[k] || null;
}

/* --- the panel element ---------------------------------------------------- */

class HealthOMatPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._panel = null;

    this._persons = null; // null = not yet loaded, [] = none configured
    this._data = {}; // entry_id -> panel_data payload
    this._entryErrors = {}; // entry_id -> error text

    this._view = "overview"; // "overview" | "detail"
    this._selectedEntry = "";
    this._tab = "drink"; // "drink" | "bp" | "wellbeing"

    this._booted = false;
    this._loading = false;
    this._fatal = null;
    this._actionError = null;
    this._formError = null;
    this._busy = false;
    this._manualBusy = false;

    this._unsub = null;
    this._pending = new Set();
    this._pendingAll = false;
    this._refreshTimer = null;

    this._renderScheduled = false;

    this._onClick = this._onClick.bind(this);
    this._onSubmit = this._onSubmit.bind(this);
    this.shadowRoot.addEventListener("click", this._onClick);
    this.shadowRoot.addEventListener("submit", this._onSubmit);
  }

  /* ---- Home Assistant panel API ------------------------------------------- */

  set hass(hass) {
    if (!hass) return;
    this._hass = hass;
    if (!this._booted) {
      this._bootstrap();
      return;
    }
    if (this._loading) return;
    // Live values come straight from hass.states; just re-render.
    this._scheduleRender();
  }

  get hass() {
    return this._hass;
  }

  set panel(panel) {
    this._panel = panel || null;
  }

  get panel() {
    return this._panel;
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._onClick);
    this.shadowRoot.removeEventListener("submit", this._onSubmit);
    this._unsubscribe();
    if (this._refreshTimer) {
      clearTimeout(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  /* ---- WS helper ---------------------------------------------------------- */

  _ws(message) {
    if (!this._hass || typeof this._hass.callWS !== "function") {
      return Promise.reject(new Error("Keine Verbindung zu Home Assistant."));
    }
    return this._hass.callWS(message);
  }

  /* ---- Bootstrap / data flow ---------------------------------------------- */

  async _bootstrap() {
    if (this._booted) return;
    this._booted = true;
    this._loading = true;
    this._fatal = null;
    this._render();
    try {
      let saved = "";
      try {
        const settings = await this._ws({ type: WS.getUiSettings });
        saved = settings && settings.selected_person ? String(settings.selected_person) : "";
      } catch (_e) {
        // UI settings are optional; never fatal.
      }
      const res = await this._ws({ type: WS.listPersons });
      this._persons = normalizePersons(res && res.persons);
      await this._loadAll();
      this._chooseStartView(saved);
      await this._subscribe();
    } catch (err) {
      this._fatal = errMsg(err);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _chooseStartView(saved) {
    const persons = this._persons || [];
    const pinned = this._configEntry();
    const pick = (entryId) => {
      this._selectedEntry = entryId;
      this._view = "detail";
    };
    if (pinned && persons.some((p) => p.entry_id === pinned)) {
      pick(pinned);
    } else if (persons.length === 1) {
      pick(persons[0].entry_id);
    } else if (saved && persons.some((p) => p.entry_id === saved)) {
      pick(saved);
    } else {
      this._view = "overview";
      this._selectedEntry = "";
    }
  }

  _configEntry() {
    const cfg = (this._panel && this._panel.config) || {};
    if (cfg.entry_id) return String(cfg.entry_id);
    if (cfg.person) {
      const wanted = String(cfg.person);
      const hit = (this._persons || []).find(
        (p) => p.entry_id === wanted || p.display_name === wanted
      );
      if (hit) return hit.entry_id;
    }
    return "";
  }

  async _loadAll() {
    const persons = this._persons || [];
    await Promise.all(persons.map((p) => this._loadEntry(p.entry_id)));
  }

  async _loadEntry(entryId) {
    if (!entryId) return;
    try {
      const data = await this._ws({ type: WS.panelData, entry_id: entryId });
      if (data) {
        this._data[entryId] = data;
        delete this._entryErrors[entryId];
      } else {
        this._entryErrors[entryId] = "Keine Daten für diese Person.";
      }
    } catch (err) {
      this._entryErrors[entryId] = errMsg(err);
    }
  }

  async _reloadEntry(entryId) {
    await this._loadEntry(entryId);
  }

  async _subscribe() {
    const conn = this._hass && this._hass.connection;
    if (!conn || typeof conn.subscribeMessage !== "function") return;
    this._unsubscribe();
    try {
      const unsub = await conn.subscribeMessage(
        (msg) => this._onRefreshEvent(msg),
        { type: WS.subscribe }
      );
      this._unsub = typeof unsub === "function" ? unsub : null;
    } catch (_e) {
      // Live push unavailable -> panel still works via hass updates / refresh.
      this._unsub = null;
    }
  }

  _unsubscribe() {
    if (typeof this._unsub === "function") {
      try {
        this._unsub();
      } catch (_e) {
        // ignore
      }
    }
    this._unsub = null;
  }

  _onRefreshEvent(msg) {
    const entryId = msg && msg.entry_id ? String(msg.entry_id) : "";
    if (entryId) this._pending.add(entryId);
    else this._pendingAll = true;
    if (this._refreshTimer) return;
    this._refreshTimer = setTimeout(() => {
      this._refreshTimer = null;
      this._flushRefresh();
    }, REFRESH_DEBOUNCE_MS);
  }

  async _flushRefresh() {
    const all = this._pendingAll;
    this._pendingAll = false;
    const ids = all
      ? (this._persons || []).map((p) => p.entry_id)
      : Array.from(this._pending);
    this._pending.clear();
    if (!ids.length) return;
    await Promise.all(ids.map((id) => this._loadEntry(id)));
    this._render();
  }

  /* ---- Navigation --------------------------------------------------------- */

  _openPerson(entryId) {
    if (!entryId) return;
    this._selectedEntry = entryId;
    this._view = "detail";
    this._actionError = null;
    this._formError = null;
    if (!this._data[entryId]) this._loadEntry(entryId).then(() => this._render());
    this._persistSelected(entryId);
    this._render();
  }

  _showOverview() {
    this._view = "overview";
    this._selectedEntry = "";
    this._actionError = null;
    this._formError = null;
    this._persistSelected("");
    this._render();
  }

  _setTab(tab) {
    this._tab = tab;
    this._actionError = null;
    this._formError = null;
    this._render();
  }

  _persistSelected(entryId) {
    if (!this._hass) return;
    this._ws({ type: WS.setUiSettings, selected_person: entryId }).catch(() => {
      // Per-user persistence is best-effort; never block the UI.
    });
  }

  async _manualRefresh() {
    if (this._manualBusy) return;
    this._manualBusy = true;
    this._actionError = null;
    this._render();
    try {
      try {
        const res = await this._ws({ type: WS.listPersons });
        this._persons = normalizePersons(res && res.persons);
      } catch (_e) {
        // keep the previous list
      }
      await this._loadAll();
      const persons = this._persons || [];
      if (!persons.length) {
        this._view = "overview";
        this._selectedEntry = "";
      } else if (
        this._view === "detail" &&
        !persons.some((p) => p.entry_id === this._selectedEntry)
      ) {
        this._showOverview();
        return;
      }
    } catch (err) {
      this._actionError = errMsg(err);
    } finally {
      this._manualBusy = false;
      this._render();
    }
  }

  /* ---- Write actions ------------------------------------------------------ */

  async _book(entryId, ml, drinkType) {
    if (!entryId || this._busy) return;
    const value = Math.round(toNumber(ml, 0));
    if (!Number.isFinite(value) || value <= 0 || value > 10000) {
      this._formError = "Bitte eine Menge zwischen 1 und 10000 ml angeben.";
      this._render();
      return;
    }
    this._busy = true;
    this._actionError = null;
    this._formError = null;
    this._render();
    try {
      const message = { type: WS.bookDrink, entry_id: entryId, ml: value };
      if (drinkType) message.drink_type = String(drinkType);
      await this._ws(message);
      await this._reloadEntry(entryId);
    } catch (err) {
      this._actionError = errMsg(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _undo(entryId) {
    if (!entryId || this._busy) return;
    this._busy = true;
    this._actionError = null;
    this._render();
    try {
      await this._ws({ type: WS.undoLast, entry_id: entryId, kind: "drink" });
      await this._reloadEntry(entryId);
    } catch (err) {
      this._actionError = errMsg(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _saveMeasurement(entryId, sys, dia, pulse, note) {
    if (!entryId || this._busy) return;
    if (!Number.isFinite(sys) || sys < 40 || sys > 300) {
      this._formError = "Systolisch muss zwischen 40 und 300 liegen.";
      this._render();
      return;
    }
    if (!Number.isFinite(dia) || dia < 20 || dia > 200) {
      this._formError = "Diastolisch muss zwischen 20 und 200 liegen.";
      this._render();
      return;
    }
    if (pulse != null && (!Number.isFinite(pulse) || pulse < 20 || pulse > 250)) {
      this._formError = "Puls muss zwischen 20 und 250 liegen.";
      this._render();
      return;
    }
    this._busy = true;
    this._actionError = null;
    this._formError = null;
    this._render();
    try {
      const message = {
        type: WS.saveMeasurement,
        entry_id: entryId,
        sys: Math.round(sys),
        dia: Math.round(dia),
      };
      if (pulse != null) message.pulse = Math.round(pulse);
      if (note) message.note = String(note);
      await this._ws(message);
      await this._reloadEntry(entryId);
    } catch (err) {
      this._actionError = errMsg(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _setWellbeing(entryId, key) {
    if (!entryId || !key || this._busy) return;
    this._busy = true;
    this._actionError = null;
    this._render();
    try {
      await this._ws({ type: WS.setWellbeing, entry_id: entryId, key: String(key) });
      await this._reloadEntry(entryId);
    } catch (err) {
      this._actionError = errMsg(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  /* ---- Live state helpers ------------------------------------------------- */

  _entityOf(data, key) {
    const map = (data && data.entities) || {};
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

  _liveNumber(data, key, fallback) {
    const value = this._stateNumber(this._entityOf(data, key), NaN);
    return Number.isFinite(value) ? value : fallback;
  }

  _liveValue(data, key, fallback) {
    return this._stateValue(this._entityOf(data, key), fallback);
  }

  _isWarning(data) {
    if (data && data.bp && data.bp.warning === true) return true;
    const map = (data && data.entities) || {};
    const entity = map.bp_warning || map.blood_pressure_warning;
    if (entity) {
      const s = this._state(entity);
      if (s && (s.state === "on" || s.state === true)) return true;
    }
    return false;
  }

  _personName(entryId) {
    const hit = (this._persons || []).find((p) => p.entry_id === entryId);
    return hit ? hit.display_name : entryId;
  }

  /* ---- Render scheduling -------------------------------------------------- */

  _scheduleRender() {
    if (this._renderScheduled) return;
    // Never clobber an open input/select while the user is typing.
    const active = this.shadowRoot.activeElement;
    if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.tagName === "SELECT")) {
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

  _render() {
    try {
      this.shadowRoot.innerHTML = this._html();
    } catch (err) {
      // Absolute last resort: never let the panel break the app shell.
      this.shadowRoot.innerHTML =
        `<style>${PANEL_CSS}</style><div class="content"><div class="msg error">` +
        `Health-O-Mat: ${escapeHtml(errMsg(err))}</div></div>`;
    }
  }

  /* ---- HTML build --------------------------------------------------------- */

  _html() {
    const body = this._bodyHtml();
    return `<style>${PANEL_CSS}</style><div class="page">${this._topbarHtml()}${body}${this._footerHtml()}</div>`;
  }

  _topbarHtml() {
    const back =
      this._view === "detail" && (this._persons || []).length > 1
        ? `<button class="icon-btn" data-action="back" type="button" aria-label="Zurück zur Übersicht">\u2190</button>`
        : "";
    const refreshing = this._manualBusy ? " disabled" : "";
    return `<div class="topbar">
        ${back}
        <div class="title"><span aria-hidden="true">\u{1F4A7}</span><span class="name">Health-O-Mat</span></div>
        <button class="icon-btn" data-action="refresh" type="button" aria-label="Aktualisieren"${refreshing}>\u21BB</button>
      </div>`;
  }

  _footerHtml() {
    return `<div class="footer">Health-O-Mat · keine medizinische Beratung</div>`;
  }

  _bodyHtml() {
    if (this._fatal) {
      return `<div class="content">${this._message(this._fatal, true)}</div>`;
    }
    if (this._persons == null) {
      return `<div class="content">${this._message("Lade Health-O-Mat\u2026", false)}</div>`;
    }
    if (!this._persons.length) {
      return `<div class="content">${this._message("Keine Person eingerichtet.", false)}</div>`;
    }
    if (this._view === "detail" && this._selectedEntry) {
      return `<div class="content">${this._detailHtml()}</div>`;
    }
    return `<div class="content">${this._overviewHtml()}</div>`;
  }

  _message(text, isError) {
    const retry = isError
      ? `<button class="btn ghost" data-action="retry" type="button">Erneut versuchen</button>`
      : "";
    return `<div class="msg${isError ? " error" : ""}">${escapeHtml(text)}${retry}</div>`;
  }

  /* ---- Overview (L2 start) ------------------------------------------------ */

  _overviewHtml() {
    const tiles = this._persons.map((p) => this._tileHtml(p)).join("");
    return `<div class="grid">${tiles}</div>`;
  }

  _tileHtml(person) {
    const entryId = person.entry_id;
    const data = this._data[entryId];
    const error = this._entryErrors[entryId];

    if (!data) {
      const note = error
        ? `<div class="tile-row muted">${escapeHtml(error)}</div>`
        : `<div class="tile-row muted">Lade\u2026</div>`;
      return `<div class="tile loading">
          <div class="tile-head"><span class="dot"></span><span class="tile-name">${escapeHtml(person.display_name)}</span></div>
          ${note}
        </div>`;
    }

    const goal = toNumber(data.goal_ml, 0);
    const fallbackMl = toNumber(data.today && data.today.ml, 0);
    const ml = this._liveNumber(data, "drinks_today", fallbackMl);
    const fallbackPct = goal > 0 ? (ml / goal) * 100 : 0;
    const percent = this._liveNumber(data, "percent", toNumber(data.today && data.today.percent, fallbackPct));
    const warn = this._isWarning(data);

    const bp = data.bp || {};
    const sys = this._liveNumber(data, "bp_sys", toNumber(bp.sys, NaN));
    const dia = this._liveNumber(data, "bp_dia", toNumber(bp.dia, NaN));
    const pulse = this._liveNumber(data, "bp_pulse", toNumber(bp.pulse, NaN));
    const bpText = Number.isFinite(sys) && Number.isFinite(dia)
      ? `${Math.round(sys)}/${Math.round(dia)}${Number.isFinite(pulse) ? ` \u00B7 ${Math.round(pulse)}` : ""}`
      : "keine Messung";

    const wb = data.wellbeing || {};
    const wbState = this._wellbeingView(data);
    const wbAt = wb.at ? relativeTime(wb.at) : "";

    const rest = goal > 0 ? Math.max(0, Math.round(goal - ml)) : null;
    const sub = goal > 0
      ? `Ziel ${fmtMl(goal)}${rest ? ` \u00B7 Rest ${fmtMl(rest)}` : ""}`
      : "Kein Tagesziel gesetzt";

    return `<button class="tile" data-action="open" data-entry="${escapeHtml(entryId)}" type="button">
        <div class="tile-head">
          <span class="dot"></span>
          <span class="tile-name">${escapeHtml(person.display_name)}</span>
          ${warn ? `<span class="status bad" title="Blutdruck oberhalb der Schwellen">\u26A0\uFE0F</span>` : ""}
        </div>
        <div class="tile-main">
          ${ringHtml(percent, { compact: true })}
          <div class="tile-stats">
            <div class="tile-ml">${fmtMl(ml)}</div>
            <div class="tile-sub">${escapeHtml(sub)}</div>
          </div>
        </div>
        <div class="tile-row"><span class="em" aria-hidden="true">\u{1FA78}</span><span>${escapeHtml(bpText)}</span>${warn ? `<span class="muted">\u00B7 \u26A0\uFE0F</span>` : ""}</div>
        <div class="tile-row"><span class="em" aria-hidden="true">${escapeHtml(wbState.emoji)}</span><span>${escapeHtml(wbState.label)}</span>${wbAt ? `<span class="muted">\u00B7 ${escapeHtml(wbAt)}</span>` : ""}</div>
      </button>`;
  }

  /* ---- Detail ------------------------------------------------------------- */

  _detailHtml() {
    const entryId = this._selectedEntry;
    const name = this._personName(entryId);
    const data = this._data[entryId];
    const error = this._entryErrors[entryId];

    const head = `<div class="person-head"><span class="dot"></span><span>${escapeHtml(name)}</span></div>`;
    const tabs = `<div class="tabs" role="tablist">
        ${this._tabButton("drink", "Trinken")}
        ${this._tabButton("bp", "Blutdruck")}
        ${this._tabButton("wellbeing", "Wohlbefinden")}
      </div>`;

    if (!data) {
      const inner = error
        ? this._message(error, true)
        : this._message("Lade Daten\u2026", false);
      return `${head}${tabs}${inner}`;
    }

    const alert = this._actionError
      ? `<div class="banner" role="alert">\u26A0\uFE0F ${escapeHtml(this._actionError)}</div>`
      : "";

    let content = "";
    if (this._tab === "bp") content = this._bpTabHtml(data, entryId);
    else if (this._tab === "wellbeing") content = this._wellbeingTabHtml(data, entryId);
    else content = this._drinkTabHtml(data, entryId);

    return `${head}${tabs}<div class="views">${alert}${content}</div>`;
  }

  _tabButton(tab, label) {
    const active = this._tab === tab ? " active" : "";
    return `<button class="tab${active}" data-action="tab" data-tab="${tab}" type="button" role="tab" aria-selected="${active ? "true" : "false"}">${escapeHtml(label)}</button>`;
  }

  /* ---- Tab: Trinken (4.2) ------------------------------------------------- */

  _drinkTabHtml(data, entryId) {
    const goal = toNumber(data.goal_ml, 0);
    const fallbackMl = toNumber(data.today && data.today.ml, 0);
    const ml = this._liveNumber(data, "drinks_today", fallbackMl);
    const fallbackPct = goal > 0 ? (ml / goal) * 100 : 0;
    const percent = this._liveNumber(data, "percent", toNumber(data.today && data.today.percent, fallbackPct));
    const goalText = goal > 0 ? fmtMl(goal) : "\u2013";
    const yesterday = toNumber(data.today && data.today.yesterday_ml, NaN);
    const count = toNumber(data.today && data.today.count, NaN);
    const pace = data.today && data.today.pace;
    const paceInfo = pace ? PACE_INFO[pace] : null;

    const stats = `<div class="tile-stats">
        <div class="kv"><span class="k">Heute</span><span class="v">${fmtMl(ml)} / ${goalText} (${Math.round(percent)}%)</span></div>
        ${Number.isFinite(yesterday) ? `<div class="kv"><span class="k">Gestern</span><span class="v">${fmtMl(yesterday)}</span></div>` : ""}
        ${Number.isFinite(count) ? `<div class="kv"><span class="k">Buchungen</span><span class="v">${Math.round(count)}</span></div>` : ""}
        ${paceInfo ? `<div><span class="status ${paceInfo.cls}">${escapeHtml(paceInfo.text)}</span></div>` : ""}
      </div>`;

    const quick = QUICK_DRINKS.map(
      (d) => `<button class="btn" data-action="book" data-ml="${d.ml}" data-drink="${escapeHtml(d.type)}" type="button"${this._busy ? " disabled" : ""}>
          <span>${escapeHtml(d.emoji)} ${escapeHtml(d.label)}</span>
          <span class="ml">${Math.round(d.ml)} ml</span>
        </button>`
    ).join("");

    const formError = this._formError
      ? `<div class="msg error">${escapeHtml(this._formError)}</div>`
      : "";

    const undo = `<button class="btn ghost" data-action="undo" type="button"${this._busy ? " disabled" : ""}>\u21A9 Undo</button>`;

    return `
      <div class="card">
        <div class="tile-main">
          ${ringHtml(percent, { sub: `${fmtMl(ml)} / ${goalText}` })}
          ${stats}
        </div>
      </div>
      <div class="card">
        <div class="muted">Schnell buchen</div>
        <div class="quick">${quick}</div>
        <form class="freetext" data-form="drink">
          <input type="text" data-field="drink-text" placeholder="z. B. Kaffee 300 ml"
            enterkeyhint="done" autocomplete="off" />
          <button class="btn" type="submit"${this._busy ? " disabled" : ""}>Buchen</button>
        </form>
        ${formError}
        ${undo}
      </div>
      ${this._breakdownHtml(data)}`;
  }

  _breakdownHtml(data) {
    const breakdown = (data.today && data.today.breakdown) || {};
    const rows = Object.keys(breakdown)
      .map((key) => [key, toNumber(breakdown[key], 0)])
      .filter((entry) => entry[1] > 0)
      .sort((a, b) => b[1] - a[1]);
    if (!rows.length) return "";
    const max = rows.reduce((acc, entry) => Math.max(acc, entry[1]), 0) || 1;
    const bars = rows
      .map(([label, value]) => `<div class="bd-row">
          <span class="muted">${escapeHtml(label)}</span>
          <span class="bd-track"><span class="bd-fill" style="width:${clamp((value / max) * 100, 2, 100).toFixed(1)}%"></span></span>
          <span>${fmtMl(value)}</span>
        </div>`)
      .join("");
    return `<div class="card">
        <div class="muted">Heute nach Getränk</div>
        ${bars}
      </div>`;
  }

  /* ---- Tab: Blutdruck (4.3) ----------------------------------------------- */

  _bpTabHtml(data, entryId) {
    const bp = data.bp || {};
    const sys = this._liveNumber(data, "bp_sys", toNumber(bp.sys, NaN));
    const dia = this._liveNumber(data, "bp_dia", toNumber(bp.dia, NaN));
    const pulse = this._liveNumber(data, "bp_pulse", toNumber(bp.pulse, NaN));
    const categoryKey = this._liveValue(data, "bp_category", bp.category || "");
    const category = categoryInfo(categoryKey);
    const warn = this._isWarning(data);
    const hasReading = Number.isFinite(sys) && Number.isFinite(dia);

    const metaParts = [];
    if (Number.isFinite(pulse)) metaParts.push(`${Math.round(pulse)} bpm`);
    if (bp.at) metaParts.push(relativeTime(bp.at));

    const head = `<div class="bp-head">
        <div class="bp-big">${hasReading ? `${Math.round(sys)} / ${Math.round(dia)}` : "\u2013 / \u2013"}</div>
        <div class="bp-meta">
          <span>systolisch / diastolisch</span>
          ${metaParts.length ? `<span>\u00B7 ${escapeHtml(metaParts.join(" \u00B7 "))}</span>` : ""}
          ${category ? `<span class="status ${category.cls}">${escapeHtml(category.label)}</span>` : ""}
        </div>
      </div>`;

    const avg = bp.avg7 || {};
    const avgParts = [];
    if (avg.sys != null && avg.dia != null) {
      avgParts.push(
        `\u00D8 7 T: ${Math.round(avg.sys)}/${Math.round(avg.dia)}${avg.pulse != null ? ` \u00B7 ${Math.round(avg.pulse)}` : ""}`
      );
    }
    const avgHtml = avgParts.length
      ? `<div class="kv"><span class="k">${escapeHtml(avgParts[0])}</span></div>`
      : "";

    const warnHtml = warn
      ? `<div class="banner" role="alert">\u26A0\uFE0F Letzte Messung oberhalb der Schwellen</div>`
      : "";

    const formError = this._formError
      ? `<div class="msg error">${escapeHtml(this._formError)}</div>`
      : "";

    const form = `<form class="card" data-form="bp">
        <div class="muted">Neue Messung</div>
        <div class="bp-inputs">
          <label class="field">Systolisch
            <input type="number" inputmode="numeric" data-field="sys" min="40" max="300" placeholder="120" />
          </label>
          <label class="field">Diastolisch
            <input type="number" inputmode="numeric" data-field="dia" min="20" max="200" placeholder="80" />
          </label>
          <label class="field">Puls
            <input type="number" inputmode="numeric" data-field="pulse" min="20" max="250" placeholder="optional" />
          </label>
        </div>
        <label class="field">Notiz
          <input type="text" data-field="note" placeholder="optional" autocomplete="off" />
        </label>
        <button class="btn" type="submit"${this._busy ? " disabled" : ""}>\u{1F4BE} Speichern</button>
        ${formError}
      </form>`;

    return `<div class="card">${head}${avgHtml}</div>${warnHtml}${form}${this._bpTrendHtml(bp)}`;
  }

  _bpTrendHtml(bp) {
    const entries = Array.isArray(bp.entries) ? bp.entries : [];
    const since = Date.now() - 7 * 24 * 3600 * 1000;
    const recent = entries
      .filter((r) => r && Number.isFinite(toNumber(r.sys, NaN)) && Number.isFinite(toNumber(r.dia, NaN)))
      .filter((r) => {
        const ts = Date.parse(r.ts);
        return !Number.isFinite(ts) || ts >= since;
      });
    if (recent.length < 2) return "";
    const low = 90;
    const high = 180;
    const bars = recent
      .slice(-21)
      .map((r) => {
        const sys = toNumber(r.sys, low);
        const dia = toNumber(r.dia, NaN);
        const h = clamp(((sys - low) / (high - low)) * 100, 6, 100);
        const title = Number.isFinite(dia) ? `${Math.round(sys)}/${Math.round(dia)}` : `${Math.round(sys)}`;
        return `<span class="bar" style="height:${h.toFixed(1)}%" title="${escapeHtml(title)}"></span>`;
      })
      .join("");
    return `<div class="card">
        <div class="muted">7-Tage-Verlauf (systolisch)</div>
        <div class="spark">${bars}</div>
      </div>`;
  }

  /* ---- Tab: Wohlbefinden (4.4) -------------------------------------------- */

  _wellbeingView(data) {
    const wb = (data && data.wellbeing) || {};
    const live = this._liveValue(data, "wellbeing", undefined);
    // entities.wellbeing is a timestamp sensor; only use its status via the
    // payload. Emoji/label always come from the (server-localised) payload.
    const key = String(wb.key || "").toLowerCase();
    const known = WELLBEING_STATES.find((s) => s.key === key);
    return {
      key,
      emoji: wb.emoji || (known && known.emoji) || "\u{1F642}",
      label: wb.label || (known && known.label) || "Keine Angabe",
      at: wb.at || (typeof live === "string" && live !== "unknown" ? live : ""),
    };
  }

  _wellbeingTabHtml(data, entryId) {
    const view = this._wellbeingView(data);
    const buttons = WELLBEING_STATES.map(
      (s) => `<button class="wb-btn${s.key === view.key ? " active" : ""}" data-action="wb" data-key="${s.key}" type="button"${this._busy ? " disabled" : ""}>
          <span class="emoji" aria-hidden="true">${s.emoji}</span>
          <span class="lbl">${escapeHtml(s.label)}</span>
        </button>`
    ).join("");

    const at = view.at ? relativeTime(view.at) : "";
    const last = `<div class="tile-row">
        <span class="em" aria-hidden="true">${escapeHtml(view.emoji)}</span>
        <span>Zuletzt: <strong>${escapeHtml(view.label)}</strong></span>
        ${at ? `<span class="muted">\u00B7 ${escapeHtml(at)}</span>` : ""}
      </div>`;

    const history = Array.isArray(data.wellbeing && data.wellbeing.history)
      ? data.wellbeing.history
      : [];
    const histHtml = history.length
      ? `<div class="card">
          <div class="muted">Verlauf</div>
          <div class="wb-history">${history
            .slice(-20)
            .map((h) => {
              const hAt = h && h.ts ? relativeTime(h.ts) : "";
              return `<span class="wb-hist" title="${escapeHtml(h && h.label ? h.label : "")}">
                  <span class="emoji" aria-hidden="true">${escapeHtml((h && h.emoji) || "\u{1F642}")}</span>
                  <span>${escapeHtml(hAt)}</span>
                </span>`;
            })
            .join("")}</div>
        </div>`
      : "";

    return `<div class="card">
        <div class="muted">Wie geht es dir?</div>
        <div class="wb-row">${buttons}</div>
        ${last}
      </div>${histHtml}`;
  }

  /* ---- Events ------------------------------------------------------------- */

  _onClick(ev) {
    const el = ev.target && ev.target.closest ? ev.target.closest("[data-action]") : null;
    if (!el) return;
    const action = el.getAttribute("data-action");
    try {
      switch (action) {
        case "open":
          this._openPerson(el.getAttribute("data-entry"));
          break;
        case "back":
          this._showOverview();
          break;
        case "refresh":
        case "retry":
          this._manualRefresh();
          break;
        case "tab":
          this._setTab(el.getAttribute("data-tab"));
          break;
        case "book":
          this._book(
            this._selectedEntry,
            toNumber(el.getAttribute("data-ml"), 0),
            el.getAttribute("data-drink") || ""
          );
          break;
        case "undo":
          this._undo(this._selectedEntry);
          break;
        case "wb":
          this._setWellbeing(this._selectedEntry, el.getAttribute("data-key"));
          break;
        default:
          break;
      }
    } catch (err) {
      this._actionError = errMsg(err);
      this._render();
    }
  }

  _onSubmit(ev) {
    const form = ev.target;
    if (!form || !form.getAttribute) return;
    const kind = form.getAttribute("data-form");
    if (kind === "drink") {
      ev.preventDefault();
      this._submitDrink();
    } else if (kind === "bp") {
      ev.preventDefault();
      this._submitBp();
    }
  }

  _submitDrink() {
    const input = this.shadowRoot.querySelector('[data-field="drink-text"]');
    const parsed = parseDrinkText(input ? input.value : "");
    if (!parsed) {
      this._formError = "Menge nicht erkannt. Beispiel: \u201EKaffee 300 ml\u201C.";
      this._render();
      return;
    }
    this._book(this._selectedEntry, parsed.ml, parsed.type);
  }

  _submitBp() {
    const read = (field) => {
      const el = this.shadowRoot.querySelector(`[data-field="${field}"]`);
      if (!el) return null;
      const raw = el.value == null ? "" : String(el.value).trim();
      if (!raw) return null;
      const n = toNumber(raw, NaN);
      return Number.isFinite(n) ? n : NaN;
    };
    const sys = read("sys");
    const dia = read("dia");
    const pulse = read("pulse");
    const noteEl = this.shadowRoot.querySelector('[data-field="note"]');
    const note = noteEl && noteEl.value ? String(noteEl.value).trim() : "";
    this._saveMeasurement(this._selectedEntry, sys, dia, pulse, note);
  }
}

if (!customElements.get(PANEL_TAG)) {
  customElements.define(PANEL_TAG, HealthOMatPanel);
}

console.info(
  `%c HEALTH-O-MAT-PANEL %c v${PANEL_VERSION} `,
  "color:#fff;background:#03a9f4;font-weight:700;border-radius:3px 0 0 3px",
  "color:#03a9f4;background:#fff;font-weight:700;border-radius:0 3px 3px 0"
);

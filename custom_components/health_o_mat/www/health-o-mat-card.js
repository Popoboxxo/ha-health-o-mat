/**
 * Health-O-Mat — Lovelace Custom Card (L1, MVP).
 *
 * Vanilla Web Component, no build toolchain, no external imports.
 * Self-contained ES2020, delivered bundled by the integration (see frontend.py)
 * and auto-registered as a Lovelace resource.
 *
 * Config:
 *   type: custom:health-o-mat-card
 *   entry_id: <config entry id>   # optional; omitted => person picker via list_persons
 *   person: <service anchor name> # optional; service-call hint for add_drink/undo
 *   quick_drinks:                 # optional; overrides the built-in presets
 *     - { label: "Glas", ml: 200, emoji: "💧" }
 *
 * Data flow (no polling, no own timer):
 *   - first `hass` set  -> load health_o_mat/panel_data (resolve entity ids)
 *   - every `hass` set  -> read live values from hass.states[entity_id]
 *   - after a write     -> one silent panel_data reload to refresh derived values
 */

const CARD_TAG = "health-o-mat-card";
const EDITOR_TAG = "health-o-mat-card-editor";
const CARD_VERSION = "0.1.0";

const DEFAULT_QUICK_DRINKS = [
  { label: "Glas Wasser", ml: 200, emoji: "\u{1F4A7}" },
  { label: "Flasche", ml: 500, emoji: "\u{1F376}" },
  { label: "Kaffee", ml: 250, emoji: "\u2615" },
  { label: "Saft", ml: 200, emoji: "\u{1F964}" },
];

const WELLBEING_EMOJI = {
  awful: "\u{1F635}",
  bad: "\u{1F635}",
  poor: "\u{1F641}",
  low: "\u{1F641}",
  neutral: "\u{1F610}",
  ok: "\u{1F610}",
  good: "\u{1F642}",
  great: "\u{1F604}",
  super: "\u{1F604}",
};

/* Wohlbefinden-Skala (Mirror von const.WELLBEING_STATES): aufsteigende
 * Qualitaet, Index + 1 = Score (1 = schlechtester … 5 = bester).
 * Die Karte ist eine eigenstaendige Datei ohne Imports — der Mirror wird
 * deshalb hier gepflegt (Panel: WELLBEING_STATES in panel-base). */
const WELLBEING_SCALE = [
  { key: "very_bad", label: "Sehr schlecht" },
  { key: "bad", label: "Schlecht" },
  { key: "okay", label: "Okay" },
  { key: "good", label: "Gut" },
  { key: "great", label: "Super" },
];

/* Anzahl der Meldungen im kompakten Trend der Karte. */
const WELLBEING_TREND_POINTS = 14;

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
  .msg button { margin-top: 10px; flex: none; min-height: 40px; }
  .editor { padding: 12px; display: flex; flex-direction: column; gap: 12px; }
  .editor label { font-size: .85rem; color: var(--secondary-text-color, #727272); }
  .editor input {
    width: 100%; box-sizing: border-box; min-height: 40px; padding: 8px 10px;
    font: inherit; border-radius: 8px; border: 1px solid var(--divider-color, rgba(0,0,0,.2));
    background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121);
  }
  .editor-hint { margin-top: 4px; font-size: .75rem; color: var(--secondary-text-color, #727272); }
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

function bpCategoryLabel(value) {
  // Friendly label for the known WHO keys; robust for unknown/legacy values.
  const raw = value == null ? "" : String(value);
  const key = raw.trim().toLowerCase();
  return BP_CATEGORY_LABELS[key] || raw;
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
    this._hass = null;
    this._data = null;
    this._persons = null;
    this._activeEntry = "";
    this._error = null;
    this._loading = false;
    this._busyMl = null;
    this._renderScheduled = false;
    this._onCardClick = this._onCardClick.bind(this);
    this._onSelectChange = this._onSelectChange.bind(this);
    this.shadowRoot.addEventListener("click", this._onCardClick);
    this.shadowRoot.addEventListener("change", this._onSelectChange);
  }

  /* ---- Lovelace card API -------------------------------------------------- */

  static getStubConfig() {
    return { entry_id: "" };
  }

  setConfig(config) {
    if (!config) throw new Error("health-o-mat-card: configuration is required");
    this._config = config;
    this._data = null;
    this._persons = null;
    this._error = null;
    this._activeEntry = activeEntryId(config, "");
    this._render();
    if (this._hass) this._loadData();
  }

  getCardSize() {
    return 5;
  }

  getConfigElement() {
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

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._onCardClick);
    this.shadowRoot.removeEventListener("change", this._onSelectChange);
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
      let entryId = activeEntryId(this._config, this._activeEntry);
      if (!this._config.entry_id) {
        const listRes = await this._hass.callWS({ type: "health_o_mat/list_persons" });
        const persons = (listRes && listRes.persons) || [];
        this._persons = persons;
        if (!persons.length) {
          this._error = "Keine Person eingerichtet.";
          this._data = null;
          this._loading = false;
          this._render();
          return;
        }
        const known = entryId && persons.some((p) => p.entry_id === entryId);
        entryId = known ? entryId : persons[0].entry_id;
        this._activeEntry = entryId;
      }
      const data = await this._hass.callWS({
        type: "health_o_mat/panel_data",
        entry_id: entryId,
      });
      this._data = data || null;
      this._error = this._data ? null : "Keine Daten für diese Person.";
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

  async _book(ml) {
    if (!this._hass || this._busyMl != null) return;
    const value = toNumber(ml, 0);
    if (value <= 0) return;
    this._busyMl = value;
    this._render();
    try {
      await Promise.resolve(
        this._hass.callService("health_o_mat", "add_drink", {
          amount_ml: value,
          person: this._servicePerson(),
        })
      );
      await this._loadData(true);
    } catch (err) {
      this._error = (err && err.message) ? err.message : String(err);
      this._render();
    } finally {
      this._busyMl = null;
      this._render();
    }
  }

  async _undo() {
    if (!this._hass || this._busyMl != null) return;
    this._busyMl = -1;
    this._render();
    try {
      await Promise.resolve(
        this._hass.callService("health_o_mat", "remove_last_entry", {
          person: this._servicePerson(),
        })
      );
      await this._loadData(true);
    } catch (err) {
      this._error = (err && err.message) ? err.message : String(err);
      this._render();
    } finally {
      this._busyMl = null;
      this._render();
    }
  }

  _quickDrinks() {
    const configured = this._config && this._config.quick_drinks;
    if (Array.isArray(configured) && configured.length) {
      const cleaned = configured
        .map((d) => ({
          label: d && d.label ? String(d.label) : "Getränk",
          ml: toNumber(d && d.ml, 0),
          emoji: d && d.emoji ? String(d.emoji) : "\u{1F4A7}",
        }))
        .filter((d) => d.ml > 0);
      if (cleaned.length) return cleaned;
    }
    return DEFAULT_QUICK_DRINKS;
  }

  /* ---- Events ------------------------------------------------------------- */

  _onCardClick(ev) {
    const target = ev.target && ev.target.closest ? ev.target.closest("[data-action]") : null;
    if (!target) return;
    const action = target.getAttribute("data-action");
    if (action === "book") {
      this._book(toNumber(target.getAttribute("data-ml"), 0));
    } else if (action === "undo") {
      this._undo();
    } else if (action === "retry") {
      this._loadData();
    }
  }

  _onSelectChange(ev) {
    const target = ev.target;
    if (!target || target.tagName !== "SELECT" || target.getAttribute("data-role") !== "person") {
      return;
    }
    this._activeEntry = target.value;
    this._persons = null; // keep the list, only reload data
    this._loadData();
  }

  _scheduleRender() {
    if (this._renderScheduled) return;
    // Do not clobber an open person dropdown.
    const active = this.shadowRoot.activeElement;
    if (active && active.tagName === "SELECT") return;
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
    const body = this._data
      ? this._body()
      : this._error
        ? this._message(this._error, true)
        : this._message("Lade Health-O-Mat\u2026", false);
    return `${style}<ha-card><div class="hom">${this._head()}${body}</div></ha-card>`;
  }

  _message(text, isError) {
    const retry = isError
      ? `<button class="ghost" data-action="retry">Erneut versuchen</button>`
      : "";
    return `<div class="msg${isError ? " error" : ""}">${escapeHtml(text)}${retry}</div>`;
  }

  _head() {
    const name = (this._data && this._data.person) || "Health-O-Mat";
    let selector = "";
    if (!this._config.entry_id && this._persons && this._persons.length) {
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
    const parts = [];
    if (areas.drink) {
      parts.push(this._hydration());
    }
    if (areas.bp) {
      parts.push(this._bloodPressure());
    }
    if (areas.wellbeing) {
      parts.push(this._wellbeing());
    }
    if (areas.drink) {
      // Quick-drink + undo actions belong to the drinking area.
      parts.push(this._actions());
    }
    return parts.length ? parts.join("") : this._message("Keine Bereiche aktiviert.", false);
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
    const at = bp.at ? this._relativeTime(bp.at) : "";
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
    const entWb = this._entity("wellbeing");
    const stateRaw = this._stateValue(entWb, undefined);
    const key = String(stateRaw != null ? stateRaw : wb.key || "").toLowerCase();
    /* Anzeige-Key: der Live-State der Entity `wellbeing` ist der Zeitstempel
     * der letzten Meldung — KEIN Wohlbefinden-Key. Als Key taugt er nur,
     * wenn er selbst einer ist; sonst bleibt der (serverseitig lokalisierte)
     * Snapshot die Quelle. */
    const displayKey = WELLBEING_SCALE.some((state) => state.key === key)
      ? key
      : String(wb.key || "").toLowerCase();
    /* Label/Emoji LIVE-FIRST: liefert die Live-Entity (`entities.wellbeing`)
     * die Attribute `label`/`emoji`, sind diese aktueller als der
     * (moeglicherweise veralteten) WS-Snapshot. Liefert die Live-Entity
     * keine Attribute, bleibt der Snapshot die Quelle — die Anzeige wird
     * dadurch nicht schlechter. */
    const emoji =
      this._stateAttribute(entWb, "emoji") ||
      wb.emoji ||
      WELLBEING_EMOJI[key] ||
      "\u{1F642}";
    const label =
      this._stateAttribute(entWb, "label") ||
      wb.label ||
      (displayKey ? displayKey.charAt(0).toUpperCase() + displayKey.slice(1) : "Keine Angabe");
    const at = (wb.at && this._relativeTime(wb.at)) || "";

    // Score (1..N): Live-Entity, sonst Server-Feld (der Server ist die
    // Wahrheit: `score: null` bedeutet "kein Score"); nur wenn das Feld
    // fehlt, wird aus dem kanonischen Key abgeleitet (aelterer Payload).
    const liveScore = this._stateNumber(this._entity("wellbeing_score"), NaN);
    const score =
      Number.isFinite(liveScore) &&
      liveScore >= 1 &&
      liveScore <= WELLBEING_SCALE.length
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
        ? `<span class="score">${score} / ${WELLBEING_SCALE.length}</span>`
        : "";
    const trend = points.length
      ? `<div class="wb-trend">${wellbeingTrendSvg(points)}</div>`
      : "";
    const sub = at ? `Zuletzt ${escapeHtml(at)}` : "Wohlbefinden";

    return `
      <div class="row">
        <span class="emoji" aria-hidden="true">${escapeHtml(emoji)}</span>
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

  _actions() {
    if (this._busyMl != null) {
      return `<div class="msg">Buchen\u2026</div>`;
    }
    const buttons = this._quickDrinks()
      .map(
        (d) => `<button data-action="book" data-ml="${d.ml}">
            <span>${escapeHtml(d.emoji)} ${escapeHtml(d.label)}</span>
            <span class="ml">${Math.round(d.ml)} ml</span>
          </button>`
      )
      .join("");
    const undo = `<button class="ghost" data-action="undo"><span>${"\u21A9"}</span><span class="ml">Undo</span></button>`;
    return `<div class="actions">${buttons}${undo}</div>`;
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
}

class HealthOMatCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._persons = null;
    this._loading = false;
    this._onValueChange = this._onValueChange.bind(this);
    this.shadowRoot.addEventListener("input", this._onValueChange);
    this.shadowRoot.addEventListener("change", this._onValueChange);
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    // Populate the person picker once (later hass updates just refresh state).
    if (first && hass && this._persons === null) this._loadPersons();
  }

  get hass() {
    return this._hass;
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

  _onValueChange(ev) {
    const target = ev.target;
    if (!target || (target.tagName !== "INPUT" && target.tagName !== "SELECT")) return;
    const key = target.getAttribute("data-key");
    if (!key) return;
    const next = Object.assign({}, this._config);
    next[key] = target.value;
    this._config = next;
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config: next }, bubbles: true, composed: true })
    );
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

  _render() {
    const current = this._config.entry_id ? String(this._config.entry_id) : "";
    let hint = "";
    if (this._persons === null) {
      hint = this._loading ? "Personen werden geladen\u2026" : "";
    } else if (!this._persons.length) {
      hint = "Keine Person eingerichtet \u2014 Karte nutzt den freien person-Anker.";
    }
    this.shadowRoot.innerHTML = `
      <style>${CARD_CSS}</style>
      <div class="editor">
        <div>
          <label for="entry_id">Person</label>
          <select id="entry_id" data-key="entry_id">${this._personOptions(current)}</select>
          ${hint ? `<div class="editor-hint">${escapeHtml(hint)}</div>` : ""}
        </div>
        <div>
          <label for="person">person \u2014 optionaler Service-Anker</label>
          <input id="person" data-key="person" type="text"
            value="${escapeHtml(this._config.person || "")}" placeholder="z. B. Caro" />
          <div class="editor-hint">Leer lassen, wenn die Karte \u00fcber die gew\u00e4hlte Person schreiben soll. Nur n\u00f6tig, wenn ein abweichender Anker (entry.data \u201eperson\u201c) angesprochen werden muss.</div>
        </div>
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

/**
 * Health-O-Mat — Sidebar Panel (L2), entry module.
 *
 * Vanilla Web Component, no build toolchain. Split into native ES modules
 * (no bundler): this file is the registered entry module
 * (`webcomponent_name`/`module_url` point here) and owns the element state,
 * WebSocket data flow, navigation and event handling. Rendering lives in the
 * sibling `-base` / `-views` / `-admin` modules.
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
 *
 * Deep-link: the URL query parameter `?person=<slug>` addresses a person page.
 * The slug is the STABLE `entry.data["person"]` — never the display name, and
 * never any health data. Opening/leaving a person pushes a history entry;
 * `popstate` restores the addressed view (overview <-> person). Reading also
 * accepts an `entry_id` as a fallback. A malformed URL never breaks the panel.
 *
 * Views (rendered by the sibling modules):
 *   - overview: responsive grid, one tile per person (L2 start)
 *   - detail:   tabs Trinken | Blutdruck | Wohlbefinden (concept 4.2–4.4),
 *               filtered by the person's feature toggles
 *   - settings: admin-only per-person admin form + person management (D7)
 *
 * Admin surface (L3): the `settings` view is reachable ONLY for
 * `hass.user.is_admin` — this UI gate is ADDITIONAL to the server gate, never a
 * substitute for it. All admin commands are server-gated; a non-admin only ever
 * receives a WS error, which is surfaced as plain text and never breaks the panel.
 *
 * Robustness: missing entities/states, per-person load errors, and WS write
 * errors are surfaced without ever breaking the panel. The settings form is
 * never re-rendered from a background `hass` update (it holds unsaved user
 * input); only explicit actions rebuild it.
 *
 * Import specifiers carry the integration version as a cache-buster query
 * parameter; tests/test_panel_js.py keeps them in sync with manifest.json.
 */

import {
  PANEL_CSS,
  WS,
  SETTINGS_LIMITS,
  SETTINGS_FALLBACKS,
  REFRESH_DEBOUNCE_MS,
  escapeHtml,
  toNumber,
  intOrNull,
  errMsg,
  wsErrorText,
  normalizeAreas,
  normalizeQuickDrinks,
  normalizePersons,
  parseDrinkText,
  personSlug,
  resolvePersonByParam,
  areasForPerson,
  enabledTabs,
  messageHtml,
} from "./health-o-mat-panel-base.js?v=0.10.0";
import { renderOverview, renderDetail } from "./health-o-mat-panel-views.js?v=0.10.0";
import {
  renderSettings,
  settingsStatusHtml,
  exportResultHtml,
  exportResultText,
} from "./health-o-mat-panel-admin.js?v=0.10.0";

const PANEL_TAG = "health-o-mat-panel";
const PANEL_VERSION = "0.2.0";

/* Person-flow target when the admin adds a person (no custom CRUD flow). */
const CONFIG_FLOW_URL = "/config/integrations/dashboard";

class HealthOMatPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._panel = null;

    this._persons = null; // null = not yet loaded, [] = none configured
    this._data = {}; // entry_id -> panel_data payload
    this._entryErrors = {}; // entry_id -> error text

    this._view = "overview"; // "overview" | "detail" | "settings"
    this._selectedEntry = "";
    this._tab = "drink"; // "drink" | "bp" | "wellbeing"

    // --- admin settings view (L3) ---
    this._settingsEntry = "";
    this._settings = {}; // entry_id -> get_settings payload
    this._settingsErrors = {}; // entry_id -> load error text
    this._quickDraft = []; // working copy of the 4 quick-drink slots
    this._settingsBusy = false;
    this._settingsStatus = null; // { ok: boolean, text: string }
    this._exportBusy = false;
    this._exportResult = null; // { ok: boolean, text: string }

    // --- person management (D7) ---
    this._adminStatus = null; // { ok: boolean, text: string }
    this._adminBusy = false;
    this._deleteTarget = ""; // entry_id awaiting inline confirmation
    this._deleteBusy = false;

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

    this._historyNavigating = false; // true while handling a popstate event
    this._popStateAttached = false;

    this._onClick = this._onClick.bind(this);
    this._onSubmit = this._onSubmit.bind(this);
    this._onChange = this._onChange.bind(this);
    this._onPopState = this._onPopState.bind(this);
    this.shadowRoot.addEventListener("click", this._onClick);
    this.shadowRoot.addEventListener("submit", this._onSubmit);
    this.shadowRoot.addEventListener("change", this._onChange);
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
    // The settings form holds unsaved user input and needs no live entity
    // values — a background render would clobber it. Only explicit actions
    // (save / person switch / reload) rebuild that view.
    if (this._view === "settings") return;
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

  connectedCallback() {
    this._addPopStateListener();
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._onClick);
    this.shadowRoot.removeEventListener("submit", this._onSubmit);
    this.shadowRoot.removeEventListener("change", this._onChange);
    this._removePopStateListener();
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

  /* ---- URL / deep-link (query parameter `person`) ------------------------- */

  _addPopStateListener() {
    if (this._popStateAttached) return;
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    window.addEventListener("popstate", this._onPopState);
    this._popStateAttached = true;
  }

  _removePopStateListener() {
    if (!this._popStateAttached) return;
    if (typeof window !== "undefined" && typeof window.removeEventListener === "function") {
      window.removeEventListener("popstate", this._onPopState);
    }
    this._popStateAttached = false;
  }

  /* Raw `person` query value (never throws on a malformed URL). */
  _queryPerson() {
    try {
      const url = new URL(window.location.href);
      return url.searchParams.get("person") || "";
    } catch (_e) {
      return "";
    }
  }

  /* Resolved person for the current URL, or null. Slug first, then entry_id. */
  _personFromUrl() {
    const raw = this._queryPerson();
    if (!raw) return null;
    return resolvePersonByParam(this._persons || [], raw);
  }

  /* Push `?person=<slug>` (or clear it for the overview) onto the history. */
  _pushUrl(person) {
    if (this._historyNavigating) return;
    if (typeof window === "undefined" || !window.history) return;
    if (typeof window.history.pushState !== "function") return;
    try {
      const url = new URL(window.location.href);
      if (person) url.searchParams.set("person", String(person));
      else url.searchParams.delete("person");
      const next = `${url.pathname}${url.search}${url.hash}`;
      const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      if (next === current) return;
      window.history.pushState({ person: person || null }, "", next);
    } catch (_e) {
      // A bad URL must never break the panel.
    }
  }

  _pushPersonUrl(slug) {
    const value = slug == null ? "" : String(slug);
    if (!value) {
      this._pushUrl("");
      return;
    }
    this._pushUrl(value);
  }

  _pushOverviewUrl() {
    this._pushUrl("");
  }

  _onPopState() {
    if (!this._booted || this._persons == null) return;
    this._historyNavigating = true;
    try {
      const person = this._personFromUrl();
      if (person) this._openPerson(person.entry_id, { silent: true });
      else this._showOverview({ silent: true });
    } catch (err) {
      this._actionError = errMsg(err);
      this._render();
    } finally {
      this._historyNavigating = false;
    }
  }

  /* ---- Bootstrap / data flow ---------------------------------------------- */

  async _bootstrap() {
    if (this._booted) return;
    this._booted = true;
    this._loading = true;
    this._fatal = null;
    // Re-register the listener (idempotent) so a re-bootstrap never duplicates it.
    this._removePopStateListener();
    this._addPopStateListener();
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
      this._applyInitialView(saved);
      await this._subscribe();
    } catch (err) {
      this._fatal = errMsg(err);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  /* A valid `?person=` deep-link wins; otherwise the previous start logic. */
  _applyInitialView(saved) {
    const viaUrl = this._personFromUrl();
    if (viaUrl) {
      this._selectedEntry = viaUrl.entry_id;
      this._view = "detail";
      return;
    }
    this._chooseStartView(saved);
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
        (p) => p.entry_id === wanted || p.person_slug === wanted || p.display_name === wanted
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
    if (this._view !== "settings") this._render();
  }

  /* ---- Navigation --------------------------------------------------------- */

  /* Open the person page. `silent` skips the pushState (popstate re-entry). */
  _openPerson(entryId, opts) {
    if (!entryId) return;
    const o = opts || {};
    this._selectedEntry = entryId;
    this._view = "detail";
    this._actionError = null;
    this._formError = null;
    if (!o.silent) this._pushPersonUrl(this._slugFor(entryId));
    if (!this._data[entryId]) this._loadEntry(entryId).then(() => this._render());
    this._persistSelected(entryId);
    this._render();
  }

  /* Return to the overview and clear the `person` query. */
  _showOverview(opts) {
    const o = opts || {};
    this._view = "overview";
    this._selectedEntry = "";
    this._actionError = null;
    this._formError = null;
    if (!o.silent) this._pushOverviewUrl();
    this._persistSelected("");
    this._render();
  }

  _slugFor(entryId) {
    const hit = (this._persons || []).find((p) => p.entry_id === entryId);
    return hit ? personSlug(hit) : "";
  }

  _setTab(tab) {
    const allowed = enabledTabs(this._areasOf(this._selectedEntry)).map((t) => t.key);
    if (!allowed.length || !allowed.includes(tab)) return;
    this._tab = tab;
    this._actionError = null;
    this._formError = null;
    this._render();
  }

  _areasOf(entryId) {
    const person = (this._persons || []).find((p) => p.entry_id === entryId) || null;
    return areasForPerson(person, this._data[entryId]);
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

  /* ---- Admin settings (L3, concept 4.5 / §8.4) ----------------------------- */

  /* UI gate only — the server gates every admin command hard as well, so this
   * is an affordance, never the boundary. */
  _isAdmin() {
    const user = this._hass && this._hass.user;
    return !!(user && user.is_admin);
  }

  _openSettings() {
    if (!this._isAdmin()) return;
    const persons = this._persons || [];
    if (!persons.length) return;
    // Prefer the person currently open in the detail view, then the last
    // settings selection, then the first person.
    const preferred = this._selectedEntry || this._settingsEntry || "";
    const entryId = persons.some((p) => p.entry_id === preferred)
      ? preferred
      : persons[0].entry_id;
    this._view = "settings";
    this._actionError = null;
    this._formError = null;
    this._settingsStatus = null;
    this._exportResult = null;
    this._adminStatus = null;
    this._deleteTarget = "";
    this._settingsEntry = entryId;
    // The quick-drink draft belongs to exactly one person — always re-sync it,
    // otherwise a cached switch would re-use the previous person's slots.
    this._syncQuickDrafts(this._settings[entryId]);
    if (!this._settings[entryId]) {
      this._loadSettings(entryId).then(() => {
        if (this._view === "settings") this._render();
      });
    }
    this._render();
  }

  _selectSettingsPerson(entryId) {
    if (!entryId || entryId === this._settingsEntry) return;
    this._settingsEntry = entryId;
    this._settingsStatus = null;
    this._exportResult = null;
    this._adminStatus = null;
    this._deleteTarget = "";
    this._syncQuickDrafts(this._settings[entryId]);
    if (!this._settings[entryId]) {
      this._loadSettings(entryId).then(() => {
        if (this._view === "settings") this._render();
      });
    }
    this._render();
  }

  async _loadSettings(entryId) {
    if (!entryId) return;
    try {
      const res = await this._ws({ type: WS.getSettings, entry_id: entryId });
      if (res && typeof res === "object") {
        this._settings[entryId] = res;
        delete this._settingsErrors[entryId];
        if (this._settingsEntry === entryId) this._syncQuickDrafts(res);
      } else {
        this._settingsErrors[entryId] = "Leere Antwort auf get_settings.";
        delete this._settings[entryId];
      }
    } catch (err) {
      this._settingsErrors[entryId] = wsErrorText(err);
    }
  }

  async _reloadSettings() {
    const entryId = this._settingsEntry;
    if (!entryId || this._settingsBusy) return;
    this._settingsBusy = true;
    this._settingsStatus = null;
    this._exportResult = null;
    this._syncSettingsButtons();
    this._updateStatusDom();
    try {
      await this._loadSettings(entryId);
      await this._reloadPersons();
    } finally {
      this._settingsBusy = false;
      this._render();
    }
  }

  async _reloadPersons() {
    try {
      const res = await this._ws({ type: WS.listPersons });
      this._persons = normalizePersons(res && res.persons);
    } catch (_e) {
      // Keep the previous list; the settings view stays usable.
    }
  }

  _syncQuickDrafts(settings) {
    this._quickDraft = normalizeQuickDrinks(settings && settings.quick_drinks);
  }

  /* DOM -> draft. Called before any add/remove and before saving so typed but
   * not-yet-submitted edits are never dropped by a re-render. */
  _readQuickDraftsFromDom() {
    const slots = this.shadowRoot.querySelectorAll("[data-slot]");
    if (!slots.length) return;
    const out = [];
    slots.forEach((slotEl) => {
      const index = slotEl.getAttribute("data-slot");
      out.push({
        key: slotEl.getAttribute("data-key") || "",
        label: String(this._slotField(index, "qd-label", "") || ""),
        ml: toNumber(this._slotField(index, "qd-ml", ""), NaN),
        icon: String(this._slotField(index, "qd-icon", "") || ""),
      });
    });
    this._quickDraft = out;
  }

  _slotField(index, field, fallback) {
    const el = this.shadowRoot.querySelector(`[data-field="${field}"][data-index="${index}"]`);
    if (!el) return fallback;
    return el.value == null ? fallback : el.value;
  }

  _addQuickSlot() {
    this._readQuickDraftsFromDom();
    if (this._quickDraft.length >= SETTINGS_LIMITS.maxQuickDrinks) return;
    this._quickDraft.push({
      key: "",
      label: "",
      ml: 250,
      icon: SETTINGS_FALLBACKS.quick_icon,
    });
    this._render();
  }

  _removeQuickSlot(index) {
    this._readQuickDraftsFromDom();
    if (!Number.isFinite(index) || index < 0 || index >= this._quickDraft.length) return;
    this._quickDraft.splice(index, 1);
    this._render();
  }

  /* --- form <-> payload ---------------------------------------------------- */

  _readField(name, fallback) {
    const el = this.shadowRoot.querySelector(`[data-field="${name}"]`);
    if (!el) return fallback;
    return el.value == null ? fallback : el.value;
  }

  _readAreaCheckboxes() {
    const read = (field) => {
      const el = this.shadowRoot.querySelector(`[data-field="${field}"]`);
      return !!(el && el.checked);
    };
    return { drink: read("area-drink"), bp: read("area-bp"), wellbeing: read("area-wellbeing") };
  }

  /* Validate + normalise the whole form. Returns { payload, errors }. */
  _collectSettingsPayload() {
    const errors = [];
    const L = SETTINGS_LIMITS;

    const goal = intOrNull(this._readField("daily_goal_ml", ""));
    if (goal === null || goal < L.goalMin || goal > L.goalMax) {
      errors.push(`Tagesziel: ganze Zahl zwischen ${L.goalMin} und ${L.goalMax} ml.`);
    }
    const reset = intOrNull(this._readField("daily_reset_hour", ""));
    if (reset === null || reset < L.resetMin || reset > L.resetMax) {
      errors.push(`Reset-Uhrzeit: ganze Zahl zwischen ${L.resetMin} und ${L.resetMax}.`);
    }
    const display = String(this._readField("person_display", "") || "").trim();
    const sys = intOrNull(this._readField("sys_threshold", ""));
    if (sys === null || sys < L.thresholdMin || sys > L.thresholdMax) {
      errors.push(`Systolische Schwelle: zwischen ${L.thresholdMin} und ${L.thresholdMax}.`);
    }
    const dia = intOrNull(this._readField("dia_threshold", ""));
    if (dia === null || dia < L.thresholdMin || dia > L.thresholdMax) {
      errors.push(`Diastolische Schwelle: zwischen ${L.thresholdMin} und ${L.thresholdMax}.`);
    }
    const retention = intOrNull(this._readField("retention_months", ""));
    if (retention === null || retention < L.retentionMin || retention > L.retentionMax) {
      errors.push(`Retention: ${L.retentionMin} (aus) bis ${L.retentionMax} Monate.`);
    }

    const lexiconEl = this.shadowRoot.querySelector('[data-field="drink_lexicon"]');
    const lexicon = lexiconEl && lexiconEl.value != null ? String(lexiconEl.value) : "";
    // Guard against wiping the lexicon with an accidental empty textarea; the
    // server re-validates the 'word=Type,ml' format and reports the line.
    if (!lexicon.trim()) {
      errors.push("Getränke-Lexikon: mindestens eine Zeile (wort=Typ,ml) erforderlich.");
    }

    const sidebarEl = this.shadowRoot.querySelector('[data-field="enable_sidebar_panel"]');
    const sidebar = !!(sidebarEl && sidebarEl.checked);

    const areas = this._readAreaCheckboxes();

    this._readQuickDraftsFromDom();
    const quick = [];
    this._quickDraft.forEach((slot, i) => {
      const label = String(slot.label == null ? "" : slot.label).trim();
      if (!label) return; // empty label = removed slot
      const ml = toNumber(slot.ml, NaN);
      if (!Number.isFinite(ml) || ml < L.quickMlMin || ml > L.quickMlMax) {
        errors.push(
          `Quick-Drink ${i + 1}: ml zwischen ${L.quickMlMin} und ${L.quickMlMax}.`
        );
        return;
      }
      quick.push({
        key: String(slot.key == null ? "" : slot.key).trim() || `slot_${i}`,
        label,
        ml: Math.round(ml),
        icon: String(slot.icon == null ? "" : slot.icon).trim() || SETTINGS_FALLBACKS.quick_icon,
      });
    });
    // The server requires at least one quick drink (vol.Length(min=1)); catch it
    // here so the user gets a precise message instead of a schema error.
    if (quick.length < L.minQuickDrinks) {
      errors.push(
        `Quick-Drinks: mindestens ${L.minQuickDrinks} Slot mit Label erforderlich.`
      );
    }

    return {
      errors,
      payload: {
        daily_goal_ml: goal,
        daily_reset_hour: reset,
        person_display: display,
        quick_drinks: quick,
        drink_lexicon: lexicon,
        sys_threshold: sys,
        dia_threshold: dia,
        retention_months: retention,
        enable_sidebar_panel: sidebar,
        areas,
      },
    };
  }

  /* Only the fields that actually differ from the loaded settings are sent
   * (PATCH semantics of `set_settings`). */
  _changedSettings(entryId, payload) {
    const current = this._settings[entryId];
    if (!current || typeof current !== "object") return Object.assign({}, payload);
    const sameNum = (a, b) => toNumber(a, NaN) === toNumber(b, NaN);
    const out = {};
    if (!sameNum(payload.daily_goal_ml, current.daily_goal_ml)) {
      out.daily_goal_ml = payload.daily_goal_ml;
    }
    if (!sameNum(payload.daily_reset_hour, current.daily_reset_hour)) {
      out.daily_reset_hour = payload.daily_reset_hour;
    }
    if (String(current.person_display == null ? "" : current.person_display) !== payload.person_display) {
      out.person_display = payload.person_display;
    }
    if (
      JSON.stringify(normalizeQuickDrinks(current.quick_drinks)) !==
      JSON.stringify(normalizeQuickDrinks(payload.quick_drinks))
    ) {
      out.quick_drinks = payload.quick_drinks;
    }
    if (
      String(current.drink_lexicon == null ? "" : current.drink_lexicon) !== payload.drink_lexicon
    ) {
      out.drink_lexicon = payload.drink_lexicon;
    }
    if (!sameNum(payload.sys_threshold, current.sys_threshold)) {
      out.sys_threshold = payload.sys_threshold;
    }
    if (!sameNum(payload.dia_threshold, current.dia_threshold)) {
      out.dia_threshold = payload.dia_threshold;
    }
    if (!sameNum(payload.retention_months, current.retention_months)) {
      out.retention_months = payload.retention_months;
    }
    if (!!current.enable_sidebar_panel !== payload.enable_sidebar_panel) {
      out.enable_sidebar_panel = payload.enable_sidebar_panel;
    }
    if (
      JSON.stringify(normalizeAreas(current.areas)) !== JSON.stringify(normalizeAreas(payload.areas))
    ) {
      out.areas = payload.areas;
    }
    return out;
  }

  async _submitSettings() {
    const entryId = this._settingsEntry;
    if (!entryId || this._settingsBusy) return;

    const collected = this._collectSettingsPayload();
    if (collected.errors.length) {
      this._settingsStatus = { ok: false, text: collected.errors.join(" ") };
      this._updateStatusDom();
      return;
    }
    const changes = this._changedSettings(entryId, collected.payload);
    if (!Object.keys(changes).length) {
      this._settingsStatus = { ok: true, text: "Keine Änderungen." };
      this._updateStatusDom();
      return;
    }

    this._settingsBusy = true;
    this._settingsStatus = { ok: true, text: "Speichere…" };
    this._syncSettingsButtons();
    this._updateStatusDom();
    try {
      const message = Object.assign({ type: WS.setSettings, entry_id: entryId }, changes);
      const res = await this._ws(message);
      if (res && typeof res === "object") {
        this._settings[entryId] = res;
        delete this._settingsErrors[entryId];
      } else {
        // Older/newer backend without an echo: re-read the authoritative state.
        await this._loadSettings(entryId);
      }
      this._syncQuickDrafts(this._settings[entryId]);
      await this._reloadPersons();
      this._settingsBusy = false;
      this._settingsStatus = { ok: true, text: "Einstellungen gespeichert." };
      // Full re-render: the form is now rebuilt from the (reloaded) server state.
      this._render();
      this._loadEntry(entryId);
    } catch (err) {
      // Keep the form DOM untouched so the user's input survives the error.
      this._settingsBusy = false;
      this._settingsStatus = { ok: false, text: wsErrorText(err) };
      this._syncSettingsButtons();
      this._updateStatusDom();
    }
  }

  async _runExport() {
    const entryId = this._settingsEntry;
    if (!entryId || this._exportBusy) return;
    const sel = this.shadowRoot.querySelector('[data-field="export_dataset"]');
    const dataset = sel && sel.value ? String(sel.value) : "all";
    this._exportBusy = true;
    this._exportResult = { ok: true, text: "Export läuft…" };
    // Targeted DOM updates only — a full re-render would drop unsaved edits.
    this._syncExportButton();
    this._updateExportResultDom();
    try {
      const res = await this._ws({ type: WS.exportCsv, entry_id: entryId, dataset });
      this._exportResult = { ok: true, text: exportResultText(res) };
    } catch (err) {
      this._exportResult = { ok: false, text: wsErrorText(err) };
    } finally {
      this._exportBusy = false;
      this._syncExportButton();
      this._updateExportResultDom();
    }
  }

  /* ---- Person management (D7) --------------------------------------------- */

  async _startPersonFlow() {
    if (!this._isAdmin() || this._adminBusy) return;
    this._adminBusy = true;
    this._adminStatus = { ok: true, text: "Starte Anlegen\u2026" };
    this._render();
    try {
      await this._ws({ type: WS.startPersonFlow });
      this._adminBusy = false;
      this._adminStatus = {
        ok: true,
        text: "Dialog ge\u00F6ffnet \u2013 bitte die neue Person dort anlegen.",
      };
      this._render();
      this._navigateToConfigFlow();
    } catch (err) {
      this._adminBusy = false;
      this._adminStatus = { ok: false, text: wsErrorText(err) };
      this._render();
    }
  }

  _navigateToConfigFlow() {
    if (typeof window === "undefined" || !window.location) return;
    const go = () => {
      try {
        window.location.href = CONFIG_FLOW_URL;
      } catch (_e) {
        // ignore
      }
    };
    if (typeof setTimeout === "function") setTimeout(go, 400);
    else go();
  }

  async _runBackup() {
    if (!this._isAdmin() || this._adminBusy) return;
    this._adminBusy = true;
    this._adminStatus = { ok: true, text: "Backup l\u00E4uft\u2026" };
    this._render();
    try {
      await this._ws({ type: WS.backup });
      this._adminStatus = { ok: true, text: "Backup erstellt." };
    } catch (err) {
      this._adminStatus = { ok: false, text: wsErrorText(err) };
    } finally {
      this._adminBusy = false;
      this._render();
    }
  }

  _beginDelete(entryId) {
    if (!this._isAdmin() || !entryId) return;
    this._deleteTarget = entryId;
    this._adminStatus = null;
    this._render();
  }

  _cancelDelete() {
    this._deleteTarget = "";
    this._render();
  }

  async _confirmDelete(entryId) {
    if (!this._isAdmin() || this._deleteBusy) return;
    const person = (this._persons || []).find((p) => p.entry_id === entryId);
    if (!person) {
      this._deleteTarget = "";
      this._render();
      return;
    }
    const slug = personSlug(person);
    const input = this.shadowRoot.querySelector('[data-field="delete-confirm"]');
    const typed = input && input.value != null ? String(input.value).trim() : "";
    // First gate: the typed slug must match exactly.
    if (!slug || typed !== slug) {
      this._adminStatus = {
        ok: false,
        text: "Die Best\u00E4tigung stimmt nicht mit dem Personen-Schl\u00FCssel \u00FCberein.",
      };
      this._render();
      return;
    }
    // Second gate: an explicit browser confirmation with the backup caveat.
    const confirmed = typeof window !== "undefined" && typeof window.confirm === "function"
      ? window.confirm(
          `\u201E${person.display_name}\u201C endg\u00FCltig l\u00F6schen? Backups k\u00F6nnen derzeit NICHT wiederhergestellt werden.`
        )
      : true;
    if (!confirmed) return;

    this._deleteBusy = true;
    this._adminStatus = { ok: true, text: "L\u00F6sche\u2026" };
    this._render();
    try {
      await this._ws({ type: WS.deletePerson, entry_id: entryId, confirm: slug });
      this._deleteBusy = false;
      this._adminStatus = { ok: true, text: "Person gel\u00F6scht." };
      await this._reloadPersons();
      this._afterPersonsChanged(entryId);
    } catch (err) {
      this._deleteBusy = false;
      this._adminStatus = { ok: false, text: wsErrorText(err) };
      this._render();
    }
  }

  /* Drop caches + selections that pointed at a removed person. */
  _afterPersonsChanged(removedEntryId) {
    delete this._data[removedEntryId];
    delete this._entryErrors[removedEntryId];
    delete this._settings[removedEntryId];
    delete this._settingsErrors[removedEntryId];
    this._deleteTarget = "";

    const persons = this._persons || [];
    if (this._selectedEntry === removedEntryId) {
      this._selectedEntry = "";
      this._pushOverviewUrl();
      this._persistSelected("");
    }
    if (!persons.length) {
      this._view = "overview";
      this._selectedEntry = "";
      this._settingsEntry = "";
      this._render();
      return;
    }
    if (
      this._view === "settings" &&
      (!this._settingsEntry || !persons.some((p) => p.entry_id === this._settingsEntry))
    ) {
      this._settingsEntry = persons[0].entry_id;
      this._syncQuickDrafts(this._settings[this._settingsEntry]);
      this._loadSettings(this._settingsEntry).then(() => {
        if (this._view === "settings") this._render();
      });
    }
    this._render();
  }

  /* --- in-place DOM updates (never clobber the form) ----------------------- */

  _syncSettingsButtons() {
    const btn = this.shadowRoot.querySelector("[data-save-button]");
    if (!btn) return;
    if (this._settingsBusy) btn.setAttribute("disabled", "");
    else btn.removeAttribute("disabled");
  }

  _syncExportButton() {
    const btn = this.shadowRoot.querySelector('[data-action="export"]');
    if (!btn) return;
    if (this._exportBusy) btn.setAttribute("disabled", "");
    else btn.removeAttribute("disabled");
  }

  _updateStatusDom() {
    const node = this.shadowRoot.querySelector("[data-settings-status]");
    if (node) node.innerHTML = settingsStatusHtml(this);
  }

  _updateExportResultDom() {
    const node = this.shadowRoot.querySelector("[data-export-result]");
    if (node) node.innerHTML = exportResultHtml(this);
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

  /* ---- HTML build (shell) ------------------------------------------------- */

  _html() {
    const body = this._bodyHtml();
    return `<style>${PANEL_CSS}</style><div class="page">${this._topbarHtml()}${body}${this._footerHtml()}</div>`;
  }

  _topbarHtml() {
    const multi = (this._persons || []).length > 1;
    const back =
      this._view === "settings" || (this._view === "detail" && multi)
        ? `<button class="icon-btn" data-action="back" type="button" aria-label="Zurück zur Übersicht">\u2190</button>`
        : "";
    const refreshing = this._manualBusy ? " disabled" : "";
    const gear =
      this._isAdmin() && this._view !== "settings"
        ? `<button class="icon-btn" data-action="settings" type="button" aria-label="Einstellungen" title="Einstellungen">\u2699\uFE0F</button>`
        : "";
    return `<div class="topbar">
        ${back}
        <div class="title"><span aria-hidden="true">\u{1F4A7}</span><span class="name">Health-O-Mat</span></div>
        ${gear}
        <button class="icon-btn" data-action="refresh" type="button" aria-label="Aktualisieren"${refreshing}>\u21BB</button>
      </div>`;
  }

  _footerHtml() {
    return `<div class="footer">Health-O-Mat · keine medizinische Beratung</div>`;
  }

  _bodyHtml() {
    if (this._fatal) {
      return `<div class="content">${messageHtml(this._fatal, true)}</div>`;
    }
    if (this._persons == null) {
      return `<div class="content">${messageHtml("Lade Health-O-Mat\u2026", false)}</div>`;
    }
    if (!this._persons.length) {
      return `<div class="content">${messageHtml("Keine Person eingerichtet.", false)}</div>`;
    }
    if (this._view === "settings" && this._isAdmin()) {
      return `<div class="content">${this._settingsHtml()}</div>`;
    }
    if (this._view === "detail" && this._selectedEntry) {
      return `<div class="content">${this._detailHtml()}</div>`;
    }
    return `<div class="content">${this._overviewHtml()}</div>`;
  }

  /* Delegating render helpers (bodies live in the views/admin modules). */
  _overviewHtml() {
    return renderOverview(this);
  }

  _detailHtml() {
    return renderDetail(this);
  }

  _settingsHtml() {
    return renderSettings(this);
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
        case "settings":
          this._openSettings();
          break;
        case "settings-reload":
          this._reloadSettings();
          break;
        case "qd-add":
          this._addQuickSlot();
          break;
        case "qd-remove":
          this._removeQuickSlot(toNumber(el.getAttribute("data-index"), -1));
          break;
        case "export":
          this._runExport();
          break;
        case "person-add":
          this._startPersonFlow();
          break;
        case "backup":
          this._runBackup();
          break;
        case "delete-begin":
          this._beginDelete(el.getAttribute("data-entry"));
          break;
        case "delete-cancel":
          this._cancelDelete();
          break;
        case "delete-confirm":
          this._confirmDelete(el.getAttribute("data-entry"));
          break;
        case "refresh":
        case "retry":
          if (this._view === "settings") this._reloadSettings();
          else this._manualRefresh();
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

  _onChange(ev) {
    const el = ev.target;
    if (!el || !el.getAttribute) return;
    if (el.getAttribute("data-action") === "settings-person") {
      this._selectSettingsPerson(el.value ? String(el.value) : "");
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
    } else if (kind === "settings") {
      ev.preventDefault();
      this._submitSettings();
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

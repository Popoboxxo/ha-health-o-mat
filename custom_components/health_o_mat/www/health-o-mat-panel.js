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
  AREA_KEYS,
  SETTINGS_LIMITS,
  SETTINGS_FALLBACKS,
  REFRESH_DEBOUNCE_MS,
  escapeHtml,
  toNumber,
  localDateTimeValue,
  intOrNull,
  errMsg,
  wsErrorText,
  normalizeAreas,
  normalizeQuickDrinks,
  normalizePersons,
  WELLBEING_STATES,
  TAB_HISTORY_KIND,
  HISTORY_LIMIT,
  parseDrinkText,
  personSlug,
  resolvePersonByParam,
  areasForPerson,
  enabledTabs,
  messageHtml,
  t,
  setUiTranslator,
  setUiLanguage,
} from "./health-o-mat-panel-base.js?v=0.16.2";
import {
  loadUiTranslations,
  t as uiTranslate,
  currentLanguage as uiCurrentLanguage,
} from "./health-o-mat-i18n.js?v=0.16.2";
import {
  renderOverview,
  renderDetail,
  handleLabReportChange,
} from "./health-o-mat-panel-views.js?v=0.16.2";
import {
  renderSettings,
  settingsStatusHtml,
  exportResultHtml,
  exportResultText,
  collectRestorePayload,
} from "./health-o-mat-panel-admin.js?v=0.16.2";

const PANEL_TAG = "health-o-mat-panel";
const PANEL_VERSION = "0.16.2";

/* Single translation source: the i18n module owns the cache, the base module
 * owns the `t()` used by every renderer. Injecting once at module load keeps
 * the base module import-free (unit-testable in Node). */
setUiTranslator(uiTranslate);

/* Rückdatierung (REQ-HOM-120): dieselbe Toleranz wie der Server. */
const TS_FUTURE_TOLERANCE_MS = 5 * 60 * 1000;

/* Person-flow target when the admin adds a person (no custom CRUD flow). */
const CONFIG_FLOW_URL = "/config/integrations/dashboard";

/* Order-independent JSON for shallow string maps (wellbeing images). */
function stableJson(value) {
  if (!value || typeof value !== "object") return "{}";
  const out = {};
  Object.keys(value)
    .sort()
    .forEach((key) => {
      out[key] = value[key];
    });
  return JSON.stringify(out);
}

class HealthOMatPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._panel = null;
    /* Language whose `common` translations are loaded ("" = not loaded yet). */
    this._uiLang = "";

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
    this._labCustomDraft = {}; // entry_id -> working copy of custom lab markers
    this._labReportDraft = {}; // entry_id -> working copy of a lab report dialog
    this._labReportOpen = {}; // entry_id -> report dialog stays open across re-renders
    this._settingsBusy = false;
    this._settingsStatus = null; // { ok: boolean, text: string }
    this._exportBusy = false;
    this._exportResult = null; // { ok: boolean, text: string }

    // --- Verlauf / Korrekturen (REQ-HOM-115) ---
    /* entryId -> kind -> { entries, error, loading, loaded, includeVoided } */
    this._history = {};
    this._historyFilter = { drinks: false, blood_pressure: false, wellbeing: false };
    this._historyBusy = false;
    this._historyConfirm = null; // { entryId, kind, id } bei Inline-Bestätigung
    this._historyStatus = null; // { kind, ok, text }
    this._historyFocus = null; // { action, kind, id } nach Void/Restore

    // --- Restore-Verwaltung (REQ-HOM-116 UI) ---
    this._restoreFiles = [];
    this._restoreFilesBusy = false;
    this._restoreFilesError = null;
    this._restoreBusy = false;
    this._restoreResult = null; // { dryRun, data }
    this._restoreError = null;
    this._restoreDraft = {
      filename: "",
      mode: "merge",
      datasets: { drinks: true, blood_pressure: true, wellbeing: true, lab_values: true },
      from: "",
      to: "",
      personMap: "",
      confirm: "",
      advanced: false,
    };

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
    /* REQ-HOM-114: vorgemerkte, noch nicht übernommene Wohlbefinden-Auswahl
     * (`{ entryId, key, score, ts }`) — nur im Bestätigungsmodus befüllt. */
    this._wbPending = null;
    /* REQ-HOM-120: Zeitpunkt-Entwürfe der `datetime-local`-Felder. Leer =
     * "jetzt"; ein Re-Render darf eine bewusste Auswahl nicht verwerfen. */
    this._tsDraft = { "drink-ts": "", "bp-ts": "", "wb-ts": "" };

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
    if (this._normalisedLanguage(hass.language) !== this._uiLang) {
      // Runtime language switch: reload resources, then re-render with the
      // new texts (the in-flight marker in the loader prevents duplicate loads).
      this._syncTranslations();
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

  _normalisedLanguage(value) {
    const raw = value == null ? "" : String(value).trim().toLowerCase();
    return raw ? raw.split(/[-_]/)[0] : "de";
  }

  /* Load the HA `common` translations for `hass.language` (never throws) and
   * keep the base module's Intl locale in sync. */
  async _syncTranslations(silent) {
    let language = "de";
    try {
      language = await loadUiTranslations(this._hass);
      language = this._normalisedLanguage(language || uiCurrentLanguage());
    } catch (_error) {
      language = this._normalisedLanguage(this._hass && this._hass.language);
    }
    this._uiLang = language;
    setUiLanguage(language);
    if (!silent) this._render();
    return language;
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
      return Promise.reject(
        new Error(t("ui_panel_no_connection", "Keine Verbindung zu Home Assistant."))
      );
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
    /* Await the (cached) translations before the first paint so an English
     * instance never flashes German labels. A failed load falls back to the
     * embedded German texts — `_syncTranslations` never throws. */
    await this._syncTranslations(true);
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
        this._entryErrors[entryId] = t("ui_common_no_data", "Keine Daten für diese Person.");
      }
    } catch (err) {
      this._entryErrors[entryId] = errMsg(err);
    }
  }

  async _reloadEntry(entryId) {
    // Bewusst OHNE `_wbPending`-Clear: ein unbeteiligter Schreibvorgang
    // (Getränk, Undo, BD) darf eine vorgemerkte Auswahl nicht verwerfen
    // (REQ-HOM-114). Verworfen wird nur in den expliziten Reset-Pfaden und
    // nach einer erfolgreichen Übernahme (`_setWellbeing`).
    await this._loadEntry(entryId);
  }

  /* ---- Verlauf / Korrekturen (REQ-HOM-115) -------------------------------- */

  /* Lazy state je Person/Ziel. `includeVoided` folgt dem Filter des Ziels. */
  _historyState(entryId, kind) {
    if (!this._history[entryId]) this._history[entryId] = {};
    const bucket = this._history[entryId];
    if (!bucket[kind]) {
      bucket[kind] = {
        entries: [],
        error: "",
        loading: false,
        loaded: false,
        includeVoided: !!this._historyFilter[kind],
      };
    }
    return bucket[kind];
  }

  async _loadHistory(entryId, kind, opts) {
    const options = opts || {};
    if (!entryId || !kind) return;
    const state = this._historyState(entryId, kind);
    if (state.loading && !options.force) return;
    if (state.loaded && !options.force) return;
    // Sequenz statt Sperre: ein erzwungener Reload (Filter/Aktion) darf einen
    // laufenden Load überholen; nur die jüngste Antwort wird übernommen.
    const seq = (state.seq || 0) + 1;
    state.seq = seq;
    state.loading = true;
    state.error = "";
    state.includeVoided = !!this._historyFilter[kind];
    if (options.render !== false) this._render();
    try {
      const res = await this._ws({
        type: WS.listHistory,
        entry_id: entryId,
        kind,
        include_voided: state.includeVoided,
      });
      if (state.seq !== seq) return;
      const entries = res && Array.isArray(res.entries) ? res.entries : [];
      state.entries = entries.slice(0, HISTORY_LIMIT);
      state.loaded = true;
    } catch (err) {
      if (state.seq !== seq) return;
      state.error = wsErrorText(err);
      state.loaded = true;
    } finally {
      if (state.seq === seq) {
        state.loading = false;
        if (options.render !== false) this._render();
      }
    }
  }

  async _loadAllHistory(entryId, opts) {
    if (!entryId) return;
    await Promise.all(
      Object.keys(TAB_HISTORY_KIND)
        .map((tab) => TAB_HISTORY_KIND[tab])
        .map((kind) => this._loadHistory(entryId, kind, Object.assign({}, opts, { render: false })))
    );
    if (!opts || opts.render !== false) this._render();
  }

  /* Nach einer eigenen Schreibaktion die betroffenen Verläufe neu holen. */
  async _refreshHistory(entryId, kinds) {
    if (!entryId) return;
    // Nur bereits geladene Verläufe nachziehen: ein noch nie geöffneter Tab
    // holt seine Liste ohnehin beim ersten Öffnen (`_setTab`).
    const loaded = (kinds || []).filter((kind) => {
      const state = this._history[entryId] && this._history[entryId][kind];
      return !!(state && state.loaded);
    });
    await Promise.all(
      loaded.map((kind) =>
        this._loadHistory(entryId, kind, { force: true, render: false })
      )
    );
  }

  _tabHistoryKind(tab) {
    return TAB_HISTORY_KIND[tab] || "";
  }

  _setHistoryFilter(kind, includeVoided) {
    const entryId = this._selectedEntry;
    if (!kind || !entryId) return;
    this._historyFilter[kind] = !!includeVoided;
    const state = this._historyState(entryId, kind);
    state.includeVoided = !!includeVoided;
    this._historyConfirm = null;
    this._historyStatus = null;
    this._loadHistory(entryId, kind, { force: true });
  }

  _beginHistoryVoid(entryId, kind, id) {
    if (!entryId || !kind || !id) return;
    this._historyConfirm = { entryId, kind, id: String(id) };
    this._historyStatus = null;
    this._render();
  }

  _cancelHistoryVoid() {
    this._historyConfirm = null;
    this._render();
  }

  async _confirmHistoryVoid(entryId, kind, id) {
    this._historyConfirm = null;
    await this._setEntryVoided(entryId, kind, id, false);
  }

  async _setEntryVoided(entryId, kind, id, restore) {
    if (!entryId || !kind || !id || this._historyBusy) return;
    this._historyBusy = true;
    this._historyStatus = null;
    this._render();
    try {
      await this._ws({
        type: restore ? WS.restoreEntry : WS.voidEntry,
        entry_id: entryId,
        kind,
        item_id: String(id),
      });
      this._historyStatus = {
        kind,
        ok: true,
        text: restore
          ? t("ui_panel_entry_restored", "Eintrag wiederhergestellt.")
          : t("ui_panel_entry_deleted", "Eintrag gelöscht."),
      };
      // Nach der Aktion steht der komplementäre Button im Fokus.
      this._historyFocus = {
        action: restore ? "history-void" : "history-restore",
        kind,
        id: String(id),
      };
      await this._reloadEntry(entryId);
      await this._refreshHistory(entryId, [kind]);
    } catch (err) {
      this._historyStatus = { kind, ok: false, text: wsErrorText(err) };
    } finally {
      this._historyBusy = false;
      this._render();
    }
  }

  /* Undo-Verfügbarkeit: die geladene History ist die Wahrheit (nur aktive
   * Einträge zählen); vor dem ersten Load dient `panel_data.undo` als
   * defensiver Fallback. */
  _canUndo(entryId, kind) {
    const state = this._history[entryId] && this._history[entryId][kind];
    if (state && state.loaded && !state.loading) {
      return state.entries.some((entry) => entry && !entry.voided_at);
    }
    const data = this._data[entryId];
    if (!data) return false;
    if (kind === "drinks") return !data.undo || data.undo.drink !== false;
    if (kind === "blood_pressure") return !data.undo || data.undo.blood_pressure !== false;
    return !!(data.wellbeing && (data.wellbeing.at || data.wellbeing.key));
  }

  _applyHistoryFocus() {
    const focus = this._historyFocus;
    this._historyFocus = null;
    if (!focus) return;
    const selector = `[data-action="${focus.action}"][data-kind="${focus.kind}"][data-id="${focus.id}"]`;
    const el = this.shadowRoot.querySelector(selector);
    if (el && typeof el.focus === "function") {
      try {
        el.focus();
      } catch (_e) {
        // Fokus ist Komfort, nie kritisch.
      }
    }
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
    if (this._selectedEntry && ids.includes(this._selectedEntry)) {
      await this._loadAllHistory(this._selectedEntry, { force: true, render: false });
    }
    if (this._view !== "settings") this._render();
  }

  /* ---- Navigation --------------------------------------------------------- */

  /* Open the person page. `silent` skips the pushState (popstate re-entry). */
  _openPerson(entryId, opts) {
    if (!entryId) return;
    const o = opts || {};
    // Personenwechsel: eine vorgemerkte Auswahl gehört zur alten Person
    // (REQ-HOM-114) und darf unter der neuen Person nicht auftauchen.
    if (this._selectedEntry && this._selectedEntry !== entryId) this._wbPending = null;
    this._selectedEntry = entryId;
    this._view = "detail";
    this._actionError = null;
    this._formError = null;
    if (!o.silent) this._pushPersonUrl(this._slugFor(entryId));
    if (!this._data[entryId]) this._loadEntry(entryId).then(() => this._render());
    // Beim Öffnen wird der Verlauf immer frisch geholt (er ist nicht Teil von
    // `panel_data` und kann sich außerhalb des Panels geändert haben).
    this._loadAllHistory(entryId, { force: true, render: false }).then(() => {
      if (this._view === "detail" && this._selectedEntry === entryId) this._render();
    });
    this._persistSelected(entryId);
    this._render();
  }

  /* Return to the overview and clear the `person` query. */
  _showOverview(opts) {
    const o = opts || {};
    this._view = "overview";
    this._selectedEntry = "";
    this._wbPending = null;
    this._actionError = null;
    this._formError = null;
    this._historyConfirm = null;
    this._historyStatus = null;
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
    const kind = this._tabHistoryKind(tab);
    if (kind) this._loadHistory(this._selectedEntry, kind);
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
    this._wbPending = null;
    this._render();
    try {
      try {
        const res = await this._ws({ type: WS.listPersons });
        this._persons = normalizePersons(res && res.persons);
      } catch (_e) {
        // keep the previous list
      }
      await this._loadAll();
      if (this._selectedEntry) {
        await this._loadAllHistory(this._selectedEntry, { force: true, render: false });
      }
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
    // Admin-Eintritt: eine vorgemerkte Auswahl gehört zur Detailansicht und
    // darf nach dem Umschalten der Option nicht wieder auftauchen (REQ-HOM-114).
    this._wbPending = null;
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
    this._restoreResult = null;
    this._restoreError = null;
    this._restoreFilesError = null;
    this._settingsEntry = entryId;
    // Admin-only: Dateiliste für die Restore-Karte (nie für Nicht-Admins).
    this._loadRestoreFiles();
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
        // Custom lab markers re-seed from the authoritative server list.
        delete this._labCustomDraft[entryId];
      } else {
        this._settingsErrors[entryId] = t(
          "ui_panel_empty_settings",
          "Leere Antwort auf get_settings."
        );
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
    // Generisch über AREA_KEYS (spiegelt areas.py): eine neue Fläche darf nie
    // durch eine vergessene Hardcodierung aus dem Settings-Payload fallen.
    const areas = {};
    AREA_KEYS.forEach((key) => {
      const el = this.shadowRoot.querySelector(`[data-field="area-${key}"]`);
      // Fehlt die Checkbox im DOM, gilt die Fläche als aktiv (wie
      // normalizeAreas für unbekannte/ältere Payloads).
      areas[key] = el ? !!el.checked : true;
    });
    return areas;
  }

  /* Validate + normalise the whole form. Returns { payload, errors }. */
  _collectSettingsPayload() {
    const errors = [];
    const L = SETTINGS_LIMITS;

    const goal = intOrNull(this._readField("daily_goal_ml", ""));
    if (goal === null || goal < L.goalMin || goal > L.goalMax) {
      errors.push(
        t("ui_panel_val_goal", "Tagesziel: ganze Zahl zwischen {min} und {max} ml.", {
          min: L.goalMin,
          max: L.goalMax,
        })
      );
    }
    const reset = intOrNull(this._readField("daily_reset_hour", ""));
    if (reset === null || reset < L.resetMin || reset > L.resetMax) {
      errors.push(
        t("ui_panel_val_reset", "Reset-Uhrzeit: ganze Zahl zwischen {min} und {max}.", {
          min: L.resetMin,
          max: L.resetMax,
        })
      );
    }
    const display = String(this._readField("person_display", "") || "").trim();
    const sys = intOrNull(this._readField("sys_threshold", ""));
    if (sys === null || sys < L.thresholdMin || sys > L.thresholdMax) {
      errors.push(
        t(
          "ui_panel_val_sys_threshold",
          "Systolische Schwelle: zwischen {min} und {max}.",
          { min: L.thresholdMin, max: L.thresholdMax }
        )
      );
    }
    const dia = intOrNull(this._readField("dia_threshold", ""));
    if (dia === null || dia < L.thresholdMin || dia > L.thresholdMax) {
      errors.push(
        t(
          "ui_panel_val_dia_threshold",
          "Diastolische Schwelle: zwischen {min} und {max}.",
          { min: L.thresholdMin, max: L.thresholdMax }
        )
      );
    }
    const retention = intOrNull(this._readField("retention_months", ""));
    if (retention === null || retention < L.retentionMin || retention > L.retentionMax) {
      errors.push(
        t("ui_panel_val_retention", "Retention: {min} (aus) bis {max} Monate.", {
          min: L.retentionMin,
          max: L.retentionMax,
        })
      );
    }
    const auditLimit = intOrNull(this._readField("audit_limit", ""));
    if (auditLimit === null || auditLimit < L.auditMin || auditLimit > L.auditMax) {
      errors.push(
        t(
          "ui_panel_val_audit",
          "Audit-Log-Limit: ganze Zahl zwischen {min} (unbegrenzt) und {max}.",
          { min: L.auditMin, max: L.auditMax }
        )
      );
    }

    const lexiconEl = this.shadowRoot.querySelector('[data-field="drink_lexicon"]');
    const lexicon = lexiconEl && lexiconEl.value != null ? String(lexiconEl.value) : "";
    // Guard against wiping the lexicon with an accidental empty textarea; the
    // server re-validates the 'word=Type,ml' format and reports the line.
    if (!lexicon.trim()) {
      errors.push(
        t(
          "ui_panel_val_lexicon",
          "Getränke-Lexikon: mindestens eine Zeile (wort=Typ,ml) erforderlich."
        )
      );
    }

    const sidebarEl = this.shadowRoot.querySelector('[data-field="enable_sidebar_panel"]');
    const sidebar = !!(sidebarEl && sidebarEl.checked);

    const confirmEl = this.shadowRoot.querySelector('[data-field="wellbeing_confirm"]');
    const wellbeingConfirm = !!(confirmEl && confirmEl.checked === true);

    const areas = this._readAreaCheckboxes();

    const wellbeingImages = {};
    WELLBEING_STATES.forEach((state) => {
      const key = state && state.key ? String(state.key) : "";
      if (!key) return;
      const value = String(this._readField(`wb-image-${key}`, "") || "").trim();
      if (value) wellbeingImages[key] = value;
    });

    this._readQuickDraftsFromDom();
    const quick = [];
    this._quickDraft.forEach((slot, i) => {
      const label = String(slot.label == null ? "" : slot.label).trim();
      if (!label) return; // empty label = removed slot
      const ml = toNumber(slot.ml, NaN);
      if (!Number.isFinite(ml) || ml < L.quickMlMin || ml > L.quickMlMax) {
        errors.push(
          t("ui_panel_val_quick_ml", "Quick-Drink {index}: ml zwischen {min} und {max}.", {
            index: i + 1,
            min: L.quickMlMin,
            max: L.quickMlMax,
          })
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
        t(
          "ui_panel_val_quick_label",
          "Quick-Drinks: mindestens {min} Slot mit Label erforderlich.",
          { min: L.minQuickDrinks }
        )
      );
    }

    // --- Laborwerte (REQ-HOM-122) ---
    // `lab_catalog` is read-only reference data from the settings payload; only
    // values that differ from the catalog default become a ref override.
    const labSettings = this._settings[this._settingsEntry] || {};
    const labCatalog =
      labSettings.lab_catalog && typeof labSettings.lab_catalog === "object"
        ? labSettings.lab_catalog
        : { categories: [], markers: {} };
    const labRefOverrides = {};
    Object.keys(labCatalog.markers || {}).forEach((key) => {
      const marker = labCatalog.markers[key] || {};
      const minEl = this.shadowRoot.querySelector(`[data-field="lab-ref-min-${key}"]`);
      const maxEl = this.shadowRoot.querySelector(`[data-field="lab-ref-max-${key}"]`);
      const minVal = minEl && minEl.value !== "" ? toNumber(minEl.value, NaN) : null;
      const maxVal = maxEl && maxEl.value !== "" ? toNumber(maxEl.value, NaN) : null;
      const entry = {};
      if (minVal != null && Number.isFinite(minVal) && minVal !== marker.ref_min) {
        entry.ref_min = minVal;
      }
      if (maxVal != null && Number.isFinite(maxVal) && maxVal !== marker.ref_max) {
        entry.ref_max = maxVal;
      }
      if (Object.keys(entry).length) labRefOverrides[key] = entry;
    });

    // Unchecked box = category hidden. A missing box (section not rendered)
    // must never be read as "hidden".
    const labHiddenCategories = (labCatalog.categories || [])
      .filter((category) => {
        const el = this.shadowRoot.querySelector(`[data-field="lab-hide-${category.key}"]`);
        return el ? el.checked === false : false;
      })
      .map((category) => category.key);

    // Missing box (section not rendered) = disclaimer stays visible.
    const hideDisclaimerEl = this.shadowRoot.querySelector(
      '[data-field="lab-hide-panel-disclaimer"]'
    );
    const labHidePanelDisclaimer = !!(hideDisclaimerEl && hideDisclaimerEl.checked);

    const labCustomMarkers = (
      this._labCustomDraft[this._settingsEntry] ||
      labSettings.lab_custom_markers ||
      []
    ).slice();

    return {
      errors,
      payload: {
        daily_goal_ml: goal,
        daily_reset_hour: reset,
        person_display: display,
        quick_drinks: quick,
        drink_lexicon: lexicon,
        wellbeing_images: wellbeingImages,
        sys_threshold: sys,
        dia_threshold: dia,
        retention_months: retention,
        audit_limit: auditLimit,
        enable_sidebar_panel: sidebar,
        wellbeing_confirm: wellbeingConfirm,
        areas,
        lab_ref_overrides: labRefOverrides,
        lab_hidden_categories: labHiddenCategories,
        lab_custom_markers: labCustomMarkers,
        lab_hide_panel_disclaimer: labHidePanelDisclaimer,
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
    if (stableJson(current.wellbeing_images) !== stableJson(payload.wellbeing_images)) {
      out.wellbeing_images = payload.wellbeing_images;
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
    if (!sameNum(payload.audit_limit, current.audit_limit)) {
      out.audit_limit = payload.audit_limit;
    }
    if (!!current.enable_sidebar_panel !== payload.enable_sidebar_panel) {
      out.enable_sidebar_panel = payload.enable_sidebar_panel;
    }
    if (!!current.wellbeing_confirm !== payload.wellbeing_confirm) {
      out.wellbeing_confirm = payload.wellbeing_confirm;
    }
    if (
      JSON.stringify(normalizeAreas(current.areas)) !== JSON.stringify(normalizeAreas(payload.areas))
    ) {
      out.areas = payload.areas;
    }
    if (stableJson(current.lab_ref_overrides) !== stableJson(payload.lab_ref_overrides)) {
      out.lab_ref_overrides = payload.lab_ref_overrides;
    }
    if (stableJson(current.lab_hidden_categories) !== stableJson(payload.lab_hidden_categories)) {
      out.lab_hidden_categories = payload.lab_hidden_categories;
    }
    if (stableJson(current.lab_custom_markers) !== stableJson(payload.lab_custom_markers)) {
      out.lab_custom_markers = payload.lab_custom_markers;
    }
    if (!!current.lab_hide_panel_disclaimer !== payload.lab_hide_panel_disclaimer) {
      out.lab_hide_panel_disclaimer = payload.lab_hide_panel_disclaimer;
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
      this._settingsStatus = { ok: true, text: t("ui_panel_no_changes", "Keine Änderungen.") };
      this._updateStatusDom();
      return;
    }

    this._settingsBusy = true;
    this._settingsStatus = { ok: true, text: t("ui_panel_saving", "Speichere…") };
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
      delete this._labCustomDraft[entryId];
      await this._reloadPersons();
      this._settingsBusy = false;
      this._settingsStatus = {
        ok: true,
        text: t("ui_panel_settings_saved", "Einstellungen gespeichert."),
      };
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
    this._exportResult = { ok: true, text: t("ui_panel_export_running", "Export läuft…") };
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
    this._adminStatus = { ok: true, text: t("ui_panel_flow_starting", "Starte Anlegen…") };
    this._render();
    try {
      await this._ws({ type: WS.startPersonFlow });
      this._adminBusy = false;
      this._adminStatus = {
        ok: true,
        text: t(
          "ui_panel_flow_opened",
          "Dialog geöffnet – bitte die neue Person dort anlegen."
        ),
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
    this._adminStatus = { ok: true, text: t("ui_panel_backup_running", "Backup läuft…") };
    this._render();
    try {
      await this._ws({ type: WS.backup });
      this._adminStatus = { ok: true, text: t("ui_panel_backup_created", "Backup erstellt.") };
    } catch (err) {
      this._adminStatus = { ok: false, text: wsErrorText(err) };
    } finally {
      this._adminBusy = false;
      this._render();
    }
  }

  /* ---- Restore-Verwaltung (REQ-HOM-116 UI) -------------------------------- */

  _restoreField(name) {
    return this.shadowRoot.querySelector(`[data-field="restore-${name}"]`);
  }

  /* DOM -> Draft. Wird vor jedem Restore-Lauf gelesen, damit getippte Werte
   * einen Busy-Re-Render überleben. */
  _syncRestoreDraftFromDom() {
    const draft = this._restoreDraft;
    const text = (name, fallback) => {
      const el = this._restoreField(name);
      return el && el.value != null ? String(el.value) : fallback;
    };
    const checked = (name, fallback) => {
      const el = this._restoreField(name);
      return el ? !!el.checked : fallback;
    };
    draft.filename = text("filename", draft.filename);
    draft.mode = text("mode", draft.mode) === "replace" ? "replace" : "merge";
    draft.from = text("from", draft.from);
    draft.to = text("to", draft.to);
    draft.personMap = text("person-map", draft.personMap);
    draft.confirm = text("confirm", draft.confirm);
    draft.datasets = {
      drinks: checked("dataset-drinks", draft.datasets.drinks),
      blood_pressure: checked("dataset-blood_pressure", draft.datasets.blood_pressure),
      wellbeing: checked("dataset-wellbeing", draft.datasets.wellbeing),
      lab_values: checked("dataset-lab_values", draft.datasets.lab_values),
    };
    const advanced = this.shadowRoot.querySelector("[data-restore-advanced]");
    if (advanced) draft.advanced = !!advanced.open;
  }

  _syncRestoreField(field, el) {
    const draft = this._restoreDraft;
    const name = String(field || "").replace(/^restore-/, "");
    if (!name) return;
    if (name === "dataset-drinks") {
      draft.datasets.drinks = !!el.checked;
    } else if (name === "dataset-blood_pressure") {
      draft.datasets.blood_pressure = !!el.checked;
    } else if (name === "dataset-wellbeing") {
      draft.datasets.wellbeing = !!el.checked;
    } else if (name === "dataset-lab_values") {
      draft.datasets.lab_values = !!el.checked;
    } else if (name === "mode") {
      draft.mode = el.value === "replace" ? "replace" : "merge";
      this._render();
    } else if (name === "filename") {
      draft.filename = el.value == null ? "" : String(el.value);
    } else if (name === "from") {
      draft.from = el.value == null ? "" : String(el.value);
    } else if (name === "to") {
      draft.to = el.value == null ? "" : String(el.value);
    } else if (name === "person-map") {
      draft.personMap = el.value == null ? "" : String(el.value);
    } else if (name === "confirm") {
      draft.confirm = el.value == null ? "" : String(el.value);
    }
  }

  async _loadRestoreFiles() {
    if (!this._isAdmin() || this._restoreFilesBusy) return;
    this._restoreFilesBusy = true;
    this._restoreFilesError = null;
    if (this._view === "settings") this._render();
    try {
      const res = await this._ws({ type: WS.listImportFiles });
      const files = res && Array.isArray(res.files)
        ? res.files.map((name) => String(name)).filter((name) => name)
        : [];
      this._restoreFiles = files;
      if (!files.includes(this._restoreDraft.filename)) {
        this._restoreDraft.filename = files.length ? files[0] : "";
      }
    } catch (err) {
      this._restoreFiles = [];
      this._restoreFilesError = wsErrorText(err);
    } finally {
      this._restoreFilesBusy = false;
      if (this._view === "settings") this._render();
    }
  }

  async _runRestore(dryRun) {
    if (!this._isAdmin() || this._restoreBusy) return;
    this._syncRestoreDraftFromDom();
    const collected = collectRestorePayload(this, { dryRun: !!dryRun });
    this._restoreError = null;
    if (!collected.ok) {
      this._restoreError = collected.error;
      this._render();
      return;
    }
    this._restoreBusy = true;
    this._restoreResult = null;
    this._render();
    try {
      const message = Object.assign(
        { type: WS.restoreBackup, dry_run: !!dryRun },
        collected.payload
      );
      const res = await this._ws(message);
      this._restoreResult = { dryRun: !!dryRun, data: res && typeof res === "object" ? res : {} };
      if (!dryRun) {
        // Personen/Settings/Entries können sich durch den Restore ändern.
        this._restoreDraft.confirm = "";
        await this._reloadPersons();
        await this._loadAll();
        const entryId = this._settingsEntry;
        if (entryId) await this._loadSettings(entryId);
        if (this._selectedEntry) {
          await this._loadAllHistory(this._selectedEntry, { force: true, render: false });
        }
      }
    } catch (err) {
      this._restoreError = wsErrorText(err);
    } finally {
      this._restoreBusy = false;
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
        text: t(
          "ui_panel_delete_confirmation_mismatch",
          "Die Bestätigung stimmt nicht mit dem Personen-Schlüssel überein."
        ),
      };
      this._render();
      return;
    }
    // Second gate: an explicit browser confirmation with the backup caveat.
    const confirmed = typeof window !== "undefined" && typeof window.confirm === "function"
      ? window.confirm(
          t(
            "ui_panel_delete_prompt",
            "„{name}“ endgültig löschen? Backups können derzeit NICHT wiederhergestellt werden.",
            { name: person.display_name }
          )
        )
      : true;
    if (!confirmed) return;

    this._deleteBusy = true;
    this._adminStatus = { ok: true, text: t("ui_panel_deleting", "Lösche…") };
    this._render();
    try {
      await this._ws({ type: WS.deletePerson, entry_id: entryId, confirm: slug });
      this._deleteBusy = false;
      this._adminStatus = { ok: true, text: t("ui_panel_person_deleted", "Person gelöscht.") };
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

  /* ---- Rückdatierung (REQ-HOM-120) ---------------------------------------- */

  _tsInput(field) {
    return this.shadowRoot.querySelector(`[data-field="${field}"]`);
  }

  /* `datetime-local`-Feld lesen und validieren.
   * Rückgabe `{ ok: true, iso }` (iso "" = jetzt) oder `{ ok: false, error }`. */
  _readEntryTs(field) {
    const el = this._tsInput(field);
    const raw = el && el.value != null ? String(el.value).trim() : "";
    if (!raw) return { ok: true, iso: "" };
    const parsed = new Date(raw);
    if (!Number.isFinite(parsed.getTime())) {
      return {
        ok: false,
        error: t("ui_panel_val_ts_invalid", "Ungültiger Zeitpunkt — bitte Datum und Uhrzeit prüfen."),
      };
    }
    if (parsed.getTime() > Date.now() + TS_FUTURE_TOLERANCE_MS) {
      return {
        ok: false,
        error: t(
          "ui_panel_val_ts_future",
          "Der Zeitpunkt liegt in der Zukunft (erlaubt sind bis zu 5 Minuten Toleranz)."
        ),
      };
    }
    if (parsed.getFullYear() < 1900) {
      return {
        ok: false,
        error: t("ui_panel_val_ts_old", "Der Zeitpunkt ist zu alt (frühestens 1900)."),
      };
    }
    return { ok: true, iso: parsed.toISOString() };
  }

  _setTsDraft(field, value) {
    this._tsDraft[field] = value == null ? "" : String(value);
    const el = this._tsInput(field);
    if (el) el.value = this._tsDraft[field] || localDateTimeValue(new Date());
  }

  _resetTs(field) {
    this._tsDraft[field] = "";
    const el = this._tsInput(field);
    if (el) el.value = "";
  }

  /* ---- Write actions ------------------------------------------------------ */

  async _book(entryId, ml, drinkType, ts) {
    if (!entryId || this._busy) return;
    if (ts === undefined) {
      const read = this._readEntryTs("drink-ts");
      if (!read.ok) {
        this._actionError = read.error;
        this._render();
        return;
      }
      ts = read.iso;
    }
    const value = Math.round(toNumber(ml, 0));
    if (!Number.isFinite(value) || value <= 0 || value > 10000) {
      this._formError = t(
        "ui_panel_val_amount",
        "Bitte eine Menge zwischen 1 und 10000 ml angeben."
      );
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
      if (ts) message.ts = String(ts);
      await this._ws(message);
      this._resetTs("drink-ts");
      await this._reloadEntry(entryId);
      await this._refreshHistory(entryId, ["drinks"]);
    } catch (err) {
      this._actionError = errMsg(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _undo(entryId, kind = "drinks") {
    if (!entryId || this._busy) return;
    const data = this._data[entryId];
    // Getränke behalten die bisherige Vorab-Prüfung (kein Fehler-Toast ohne
    // buchbare Buchung); BD/WB fragen dieselbe Verfügbarkeit über `_canUndo`.
    if (kind === "drinks" && data && data.undo && data.undo.drink === false) return;
    if (kind !== "drinks" && !this._canUndo(entryId, kind)) return;
    this._busy = true;
    this._actionError = null;
    this._historyStatus = null;
    this._render();
    try {
      await this._ws({ type: WS.undoLast, entry_id: entryId, kind });
      await this._reloadEntry(entryId);
      await this._refreshHistory(entryId, [kind]);
    } catch (err) {
      this._actionError = errMsg(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _saveMeasurement(entryId, sys, dia, pulse, note, ts) {
    if (!entryId || this._busy) return;
    if (ts === undefined) {
      const read = this._readEntryTs("bp-ts");
      if (!read.ok) {
        this._formError = read.error;
        this._render();
        return;
      }
      ts = read.iso;
    }
    if (!Number.isFinite(sys) || sys < 40 || sys > 300) {
      this._formError = t(
        "ui_panel_val_bp_sys",
        "Systolisch muss zwischen 40 und 300 liegen."
      );
      this._render();
      return;
    }
    if (!Number.isFinite(dia) || dia < 20 || dia > 200) {
      this._formError = t(
        "ui_panel_val_bp_dia",
        "Diastolisch muss zwischen 20 und 200 liegen."
      );
      this._render();
      return;
    }
    if (pulse != null && (!Number.isFinite(pulse) || pulse < 20 || pulse > 250)) {
      this._formError = t("ui_panel_val_bp_pulse", "Puls muss zwischen 20 und 250 liegen.");
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
      if (ts) message.ts = String(ts);
      await this._ws(message);
      this._resetTs("bp-ts");
      await this._reloadEntry(entryId);
      await this._refreshHistory(entryId, ["blood_pressure"]);
    } catch (err) {
      this._actionError = errMsg(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  /* ---- Wohlbefinden-Bestätigung (REQ-HOM-114) ------------------------------ */

  /* Bestätigungsmodus je Person. Fehlt der Schlüssel (älteres Backend),
   * bleibt das bisherige Sofort-Verhalten aktiv. */
  _wellbeingConfirmEnabled(entryId) {
    const data = entryId ? this._data[entryId] : null;
    return !!(data && data.wellbeing_confirm === true);
  }

  _wbPendingFor(entryId) {
    const pending = this._wbPending;
    if (!pending || pending.entryId !== entryId) return null;
    return pending;
  }

  /* Merkt eine Auswahl nur vor — gesendet wird sie erst mit „Übernehmen". */
  _stageWellbeing(entryId, key, score, ts) {
    if (!entryId || (!key && score == null)) return;
    if (ts === undefined) {
      const read = this._readEntryTs("wb-ts");
      if (!read.ok) {
        this._formError = read.error;
        this._render();
        return;
      }
      ts = read.iso;
    }
    this._wbPending = {
      entryId,
      key: key == null ? "" : String(key),
      score: score == null ? null : Number(score),
      ts: ts == null ? "" : String(ts),
    };
    this._actionError = null;
    this._formError = null;
    this._render();
  }

  async _confirmWellbeing() {
    const pending = this._wbPendingFor(this._selectedEntry);
    if (!pending || this._busy) return;
    await this._setWellbeing(pending.entryId, pending.key || null, pending.score, pending.ts || "");
  }

  async _setWellbeing(entryId, key, score, ts = "") {
    if (!entryId || (!key && score == null) || this._busy) return;
    this._busy = true;
    this._actionError = null;
    this._formError = null;
    this._render();
    try {
      const message = { type: WS.setWellbeing, entry_id: entryId };
      if (key) message.key = String(key);
      else message.score = Number(score);
      if (ts) message.ts = String(ts);
      await this._ws(message);
      this._resetTs("wb-ts");
      await this._reloadEntry(entryId);
      await this._refreshHistory(entryId, ["wellbeing"]);
      // Erst die erfolgreiche Übernahme erledigt die Vormerkung; bei einem
      // Fehler bleibt sie für den nächsten Versuch stehen (REQ-HOM-114).
      if (this._wbPendingFor(entryId)) this._wbPending = null;
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
      try {
        this._applyHistoryFocus();
      } catch (_e) {
        // Fokus ist Komfort, nie ein Render-Grund.
      }
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
        ? `<button class="icon-btn" data-action="back" type="button" aria-label="${escapeHtml(
            t("ui_panel_back_aria", "Zurück zur Übersicht")
          )}">\u2190</button>`
        : "";
    const refreshing = this._manualBusy ? " disabled" : "";
    const gear =
      this._isAdmin() && this._view !== "settings"
        ? `<button class="icon-btn" data-action="settings" type="button" aria-label="${escapeHtml(
            t("ui_panel_settings_aria", "Einstellungen")
          )}" title="${escapeHtml(
            t("ui_panel_settings_aria", "Einstellungen")
          )}">\u2699\uFE0F</button>`
        : "";
    return `<div class="topbar">
        ${back}
        <div class="title"><span aria-hidden="true">\u{1F4A7}</span><span class="name">Health-O-Mat</span></div>
        ${gear}
        <button class="icon-btn" data-action="refresh" type="button" aria-label="${escapeHtml(
          t("ui_panel_refresh_aria", "Aktualisieren")
        )}"${refreshing}>\u21BB</button>
      </div>`;
  }

  _footerHtml() {
    return `<div class="footer">${escapeHtml(
      t("ui_panel_footer", "Health-O-Mat · keine medizinische Beratung")
    )}</div>`;
  }

  _bodyHtml() {
    if (this._fatal) {
      return `<div class="content">${messageHtml(this._fatal, true)}</div>`;
    }
    if (this._persons == null) {
      return `<div class="content">${messageHtml(
        t("ui_panel_loading_app", "Lade Health-O-Mat…"),
        false
      )}</div>`;
    }
    if (!this._persons.length) {
      return `<div class="content">${messageHtml(
        t("ui_common_no_person", "Keine Person eingerichtet."),
        false
      )}</div>`;
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
    const tsQuick = /^(drink|bp|wb)-ts-(now|yesterday)$/.exec(action || "");
    if (tsQuick) {
      const when = new Date();
      if (tsQuick[2] === "yesterday") when.setDate(when.getDate() - 1);
      this._setTsDraft(`${tsQuick[1]}-ts`, localDateTimeValue(when));
      return;
    }
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
        case "lab-custom-add": {
          const entryId = this._settingsEntry;
          if (!entryId) break;
          const name = String(this._readField("lab-custom-name", "") || "").trim();
          const unit = String(this._readField("lab-custom-unit", "") || "").trim();
          if (!name || !unit) break;
          const category = String(
            this._readField("lab-custom-category", "") || "other"
          ).trim() || "other";
          const refMin = toNumber(this._readField("lab-custom-ref-min", ""), NaN);
          const refMax = toNumber(this._readField("lab-custom-ref-max", ""), NaN);
          const altUnit = String(this._readField("lab-custom-alt-unit", "") || "").trim();
          const altFactor = toNumber(this._readField("lab-custom-alt-factor", ""), NaN);
          const marker = { name, unit, category };
          if (Number.isFinite(refMin)) marker.ref_min = refMin;
          if (Number.isFinite(refMax)) marker.ref_max = refMax;
          if (altUnit && Number.isFinite(altFactor)) {
            marker.alt_unit = { unit: altUnit, factor_to_canonical: altFactor };
          }
          const list =
            this._labCustomDraft[entryId] ||
            (this._settings[entryId] || {}).lab_custom_markers ||
            [];
          this._labCustomDraft[entryId] = list.concat([marker]);
          this._render();
          break;
        }
        case "lab-custom-remove": {
          const entryId = this._settingsEntry;
          if (!entryId) break;
          const index = toNumber(el.getAttribute("data-index"), -1);
          const list =
            this._labCustomDraft[entryId] ||
            (this._settings[entryId] || {}).lab_custom_markers ||
            [];
          if (!Number.isFinite(index) || index < 0 || index >= list.length) break;
          this._labCustomDraft[entryId] = list.filter((_item, i) => i !== index);
          this._render();
          break;
        }
        case "lab-ref-reset": {
          const marker = el.getAttribute("data-marker") || "";
          if (!marker) break;
          const minEl = this.shadowRoot.querySelector(`[data-field="lab-ref-min-${marker}"]`);
          const maxEl = this.shadowRoot.querySelector(`[data-field="lab-ref-max-${marker}"]`);
          if (minEl) minEl.value = "";
          if (maxEl) maxEl.value = "";
          break;
        }
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
        case "book": {
          const ts = this._readEntryTs("drink-ts");
          if (!ts.ok) {
            this._actionError = ts.error;
            this._render();
            break;
          }
          this._book(
            this._selectedEntry,
            toNumber(el.getAttribute("data-ml"), 0),
            el.getAttribute("data-drink") || "",
            ts.iso
          );
          break;
        }
        case "undo":
          this._undo(this._selectedEntry, el.getAttribute("data-kind") || "drinks");
          break;
        case "history-filter":
          this._setHistoryFilter(
            el.getAttribute("data-kind"),
            el.getAttribute("data-voided") === "1"
          );
          break;
        case "history-void":
          this._beginHistoryVoid(
            this._selectedEntry,
            el.getAttribute("data-kind"),
            el.getAttribute("data-id")
          );
          break;
        case "history-void-confirm":
          this._confirmHistoryVoid(
            this._selectedEntry,
            el.getAttribute("data-kind"),
            el.getAttribute("data-id")
          );
          break;
        case "history-void-cancel":
          this._cancelHistoryVoid();
          break;
        case "history-restore":
          this._setEntryVoided(
            this._selectedEntry,
            el.getAttribute("data-kind"),
            el.getAttribute("data-id"),
            true
          );
          break;
        case "restore-files-refresh":
          this._loadRestoreFiles();
          break;
        case "restore-dry-run":
          this._runRestore(true);
          break;
        case "restore-apply":
          this._runRestore(false);
          break;
        case "wb": {
          const ts = this._readEntryTs("wb-ts");
          if (!ts.ok) {
            this._formError = ts.error;
            this._render();
            break;
          }
          if (this._wellbeingConfirmEnabled(this._selectedEntry)) {
            this._stageWellbeing(this._selectedEntry, el.getAttribute("data-key"), null, ts.iso);
          } else {
            this._setWellbeing(this._selectedEntry, el.getAttribute("data-key"), null, ts.iso);
          }
          break;
        }
        case "wb-confirm":
          this._confirmWellbeing();
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
    const field = el.getAttribute("data-field") || "";
    if (field.startsWith("lab-report-")) {
      const rerender = handleLabReportChange(
        this,
        this._selectedEntry,
        field,
        el.value == null ? "" : String(el.value)
      );
      if (rerender) this._render();
      return;
    }
    if (field.endsWith("-ts")) {
      this._tsDraft[field] = el.value == null ? "" : String(el.value);
      return;
    }
    if (field.startsWith("restore-")) {
      this._syncRestoreField(field, el);
      return;
    }
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
    } else if (kind === "wellbeing") {
      ev.preventDefault();
      this._submitWellbeing();
    } else if (kind === "settings") {
      ev.preventDefault();
      this._submitSettings();
    }
  }

  _submitDrink() {
    const input = this.shadowRoot.querySelector('[data-field="drink-text"]');
    const parsed = parseDrinkText(input ? input.value : "");
    if (!parsed) {
      this._formError = t(
        "ui_panel_drink_parse_error",
        "Menge nicht erkannt. Beispiel: „Kaffee 300 ml“."
      );
      this._render();
      return;
    }
    const ts = this._readEntryTs("drink-ts");
    if (!ts.ok) {
      this._formError = ts.error;
      this._render();
      return;
    }
    this._book(this._selectedEntry, parsed.ml, parsed.type, ts.iso);
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
    const ts = this._readEntryTs("bp-ts");
    if (!ts.ok) {
      this._formError = ts.error;
      this._render();
      return;
    }
    this._saveMeasurement(this._selectedEntry, sys, dia, pulse, note, ts.iso);
  }

  _submitWellbeing() {
    const el = this.shadowRoot.querySelector('[data-field="wb-score"]');
    const raw = el && el.value != null ? String(el.value).trim() : "";
    const score = Number(raw);
    const scale = this._data[this._selectedEntry] && Array.isArray(this._data[this._selectedEntry].wellbeing_scale)
      ? this._data[this._selectedEntry].wellbeing_scale.length
      : 10;
    if (!/^\d+$/.test(raw) || !Number.isInteger(score) || score < 1 || score > scale) {
      this._formError = t(
        "ui_panel_val_wb",
        "Bitte eine ganze Zahl zwischen 1 und {max} eingeben.",
        { max: scale }
      );
      this._render();
      return;
    }
    const ts = this._readEntryTs("wb-ts");
    if (!ts.ok) {
      this._formError = ts.error;
      this._render();
      return;
    }
    if (this._wellbeingConfirmEnabled(this._selectedEntry)) {
      this._stageWellbeing(this._selectedEntry, null, score, ts.iso);
      return;
    }
    this._setWellbeing(this._selectedEntry, null, score, ts.iso);
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

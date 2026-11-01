/**
 * Health-O-Mat — Laborwerte Lovelace card (REQ-HOM-122).
 *
 * Standalone custom card, same base patterns as health-o-mat-card.js
 * (person_mode/person_filter/default_person, HA CSS variables, no external
 * chart library) — kept separate per the spec (§7.1): the existing card
 * already has nine show_* flags, a tenth subject area would overload its
 * editor.
 *
 * The card is a SEPARATE custom element loaded directly by Lovelace and must
 * not import from the panel module graph (the panel's static path is not
 * guaranteed to be loaded in every dashboard context). The lab helpers
 * (badge/subline/sparkline) are therefore small, self-contained copies of
 * the panel helpers — intentional duplication, no third shared module.
 *
 * Data flow (no polling, no own timer):
 *   - first `hass` set        -> resolve person + load health_o_mat/panel_data
 *   - after a write           -> one silent panel_data reload
 *   - writes go through `hass.connection.sendMessagePromise` (the same WS
 *     path as the existing card) so UI errors stay a card message instead of
 *     a Home-Assistant service error toast.
 */

const CARD_TAG = "health-o-mat-labs-card";
const EDITOR_TAG = "health-o-mat-labs-card-editor";
const CARD_VERSION = "0.17.2";

const PERSON_MODES = ["selector", "fixed"];

/* Gleiche Zukunfts-Toleranz wie Karte/Server (REQ-HOM-120). */
const TS_FUTURE_TOLERANCE_MS = 5 * 60 * 1000;

// UI-Soft-Cap des Bericht-Dialogs (Render-Schutz). Server-Limit bleibt 200 (§2.5).
const LAB_REPORT_MAX_ROWS_UI = 60;

/* ---- Self-contained helpers (no imports) --------------------------------- */

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function toNumber(value, fallback) {
  const number = typeof value === "number" ? value : parseFloat(value);
  return Number.isFinite(number) ? number : fallback;
}

/* Defensive Boolean-Aufloesung (echte Booleans + "on"/"off" aus YAML). */
function toBool(value, fallback) {
  if (value === true || value === false) return value;
  if (typeof value === "string") {
    const text = value.trim().toLowerCase();
    if (text === "true" || text === "on" || text === "yes" || text === "1") return true;
    if (text === "false" || text === "off" || text === "no" || text === "0") return false;
  }
  return fallback;
}

function normalizeStringList(value) {
  if (!Array.isArray(value)) return [];
  const out = [];
  for (const item of value) {
    const text = item == null ? "" : String(item).trim();
    if (text && !out.includes(text)) out.push(text);
  }
  return out;
}

/* UI-Sprache (BCP-47 wie "en-GB" -> "en"). Die Karte lädt keine
 * Übersetzungsressourcen; sie braucht die Sprache nur für die
 * sprachabhängigen Katalog-Namen (`name_de`/`name_en` aus `panel_data`). */
let _language = "de";

function setCardLanguage(hass) {
  const raw = hass && hass.language != null ? String(hass.language).trim().toLowerCase() : "";
  if (raw) _language = raw.split(/[-_]/)[0] || "de";
}

function labDisplayName(item, fallback) {
  const entry = item && typeof item === "object" ? item : {};
  const de = entry.name_de || entry.name;
  const en = entry.name_en || de;
  const chosen = _language === "en" ? en : de;
  if (chosen) return String(chosen);
  return fallback == null ? "" : String(fallback);
}

/* Kartenlokale Übersetzungen: die Karte lädt keine HA-Ressourcen, braucht aber
 * den Disclaimer sprachabhängig. Die Keys sind identisch zu `common` in
 * strings.json; ein Test pinnt die Gleichheit der Texte. */
const CARD_TEXT = {
  de: {
    ui_card_lab_disclaimer:
      "⚠️ Hinweis: keine medizinische Beratung — Richtwerte, keine Diagnose. Referenzbereiche in den Einstellungen anpassen.",
    // REQ-HOM-133 (#73): Warnung im Einheiten-Dropdown (Pflicht-Marker).
    ui_panel_lab_unit_required: "Einheit erforderlich",
  },
  en: {
    ui_card_lab_disclaimer:
      "⚠️ Note: not medical advice — reference values, not a diagnosis. Adjust reference ranges in the settings.",
    ui_panel_lab_unit_required: "Unit required",
  },
};

function cardText(key) {
  const language = _language === "en" ? "en" : "de";
  return (CARD_TEXT[language] && CARD_TEXT[language][key]) || CARD_TEXT.de[key] || "";
}

/* ✓ im Referenzbereich, ⚠ außerhalb, – kein Referenzbereich hinterlegt. */
function labBadge(inRange) {
  if (inRange === true) return `<span class="status good" aria-hidden="true">✓</span>`;
  if (inRange === false) return `<span class="status bad" aria-hidden="true">⚠️</span>`;
  return `<span class="muted" aria-hidden="true">–</span>`;
}

/* Subzeile "↷ eingegeben als <value> <unit>" — nur bei abweichender
 * Eingabe-Einheit (§7.1), kein Rauschen im Normalfall. */
function labReportedSubline(marker) {
  if (!marker || marker.reported_unit == null || marker.reported_unit === marker.unit) {
    return "";
  }
  return `<div class="lab-subline muted">↷ eingegeben als ${escapeHtml(
    marker.reported_value
  )} ${escapeHtml(marker.reported_unit)}</div>`;
}

/* Kompakte Sparkline (reines SVG, kein Chart-Framework). */
function labSparkline(history) {
  const points = (Array.isArray(history) ? history : []).filter((point) =>
    Number.isFinite(toNumber(point && point.value, NaN))
  );
  if (points.length < 2) return `<span class="muted">–</span>`;
  const values = points.map((point) => toNumber(point.value, 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 60;
  const height = 20;
  const coords = values
    .map(
      (value, index) =>
        `${((index / (values.length - 1)) * width).toFixed(1)},${(
          height -
          ((value - min) / span) * height
        ).toFixed(1)}`
    )
    .join(" ");
  return `<svg class="lab-sparkline" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" width="${width}" height="${height}" aria-hidden="true"><polyline points="${coords}" fill="none" stroke="var(--primary-color)" stroke-width="1.5" /></svg>`;
}

function formatLabValue(value) {
  const number = toNumber(value, NaN);
  if (!Number.isFinite(number)) return "";
  try {
    return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 3 }).format(number);
  } catch (_error) {
    return String(number);
  }
}

function referenceText(marker) {
  if (!marker) return "";
  const min = marker.ref_min;
  const max = marker.ref_max;
  if (min == null && max == null) return "";
  const unit = marker.unit ? ` ${marker.unit}` : "";
  if (min != null && max != null) {
    return `Referenz: ${formatLabValue(min)}–${formatLabValue(max)}${unit}`;
  }
  if (min != null) return `Referenz: ≥ ${formatLabValue(min)}${unit}`;
  return `Referenz: ≤ ${formatLabValue(max)}${unit}`;
}

/* 🔗-Icon für `report_ref`: URL -> klickbarer Link (neuer Tab), sonst
 * Klartext-Tooltip "Quelle: …" (rein clientseitige Fallunterscheidung). */
function reportRefHtml(reportRef) {
  const raw = reportRef == null ? "" : String(reportRef).trim();
  if (!raw) return "";
  if (/^https?:\/\//i.test(raw)) {
    return `<a class="lab-ref" href="${escapeHtml(raw)}" target="_blank" rel="noopener" title="${escapeHtml(
      raw
    )}" aria-label="Quelle öffnen">🔗</a>`;
  }
  return `<span class="lab-ref" title="Quelle: ${escapeHtml(raw)}" aria-label="Quelle">🔗</span>`;
}

function formatRelativeTs(ts) {
  if (!ts) return "";
  const then = new Date(ts).getTime();
  if (!Number.isFinite(then)) return "";
  const diffSeconds = Math.round((then - Date.now()) / 1000);
  const abs = Math.abs(diffSeconds);
  try {
    const formatter = new Intl.RelativeTimeFormat("de", { numeric: "auto" });
    if (abs < 60) return formatter.format(diffSeconds, "second");
    if (abs < 3600) return formatter.format(Math.round(diffSeconds / 60), "minute");
    if (abs < 86400) return formatter.format(Math.round(diffSeconds / 3600), "hour");
    return formatter.format(Math.round(diffSeconds / 86400), "day");
  } catch (_error) {
    return "";
  }
}

/* <option>-Liste des Marker-Pickers, alphabetisch nach Anzeigename. Das
 * `data-unit`-Attribut fuellt den Einheiten-Platzhalter ohne Re-Render. */
function labMarkerOptionsHtml(markers, selectedKey) {
  return Object.entries(markers || {})
    .sort(([, a], [, b]) =>
      labDisplayName(a, "").localeCompare(labDisplayName(b, ""))
    )
    .map(
      ([key, marker]) =>
        `<option value="${escapeHtml(key)}" data-unit="${escapeHtml(
          marker && marker.unit
        )}"${key === selectedKey ? " selected" : ""}>${escapeHtml(
          labDisplayName(marker, key)
        )}${marker && marker.unit ? ` (${escapeHtml(marker.unit)})` : ""}</option>`
    )
    .join("");
}

function errorMessage(err) {
  const raw = err && err.message ? String(err.message) : String(err == null ? "" : err);
  const text = raw.trim();
  const known = {
    unknown_marker: "Unbekannter Marker.",
    unit_required: "Für diesen Marker ist eine Einheit erforderlich.",
    unsupported_unit: "Diese Einheit wird für den Marker nicht unterstützt.",
    invalid_value: "Ungültiger Wert.",
  };
  return known[text] || text || "Speichern fehlgeschlagen.";
}

/* Strukturierte Batch-Fehler (§2.4/§3): `sendMessagePromise` löst bei
 * {"ok": false} NICHT ab — der Aufrufer muss die Envelope selbst prüfen. */
function resultError(result) {
  if (!result || result.ok !== false) return "";
  const error = result.error && typeof result.error === "object" ? result.error : {};
  return error.message || error.code || "Speichern fehlgeschlagen.";
}

function reportErrorMessage(err) {
  const message = err && err.message ? String(err.message) : String(err == null ? "" : err);
  return message.trim() || "Speichern fehlgeschlagen.";
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

function normalizeCardConfig(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  const entryId = source.entry_id ? String(source.entry_id) : "";
  const requestedMode = source.person_mode ? String(source.person_mode).toLowerCase() : "";
  return {
    entryId,
    personMode: PERSON_MODES.includes(requestedMode)
      ? requestedMode
      : entryId
        ? "fixed"
        : "selector",
    personFilter: normalizeStringList(source.person_filter),
    defaultPerson: source.default_person ? String(source.default_person) : "",
    showCategories: normalizeStringList(source.show_categories),
    showTrend: toBool(source.show_trend, true),
    allowManualEntry: toBool(source.allow_manual_entry, true),
    showDisclaimer: toBool(source.show_disclaimer, true),
  };
}

const EMPTY_DRAFT = () => ({ marker: "", value: "", unit: "", ts: "", reportRef: "" });

const EMPTY_REPORT_ROW = () => ({ marker: "", value: "", unit: "" });
const EMPTY_REPORT_DRAFT = () => ({
  ts: "",
  reportRef: "",
  rows: [EMPTY_REPORT_ROW()],
});

const CARD_CSS = `
  :host { display: block; }
  ha-card {
    background: var(--card-background-color, var(--ha-card-background, #fff));
    color: var(--primary-text-color, #212121);
    border-radius: var(--ha-card-border-radius, 12px);
    overflow: hidden;
  }
  .labs-card { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
  .labs-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
  .labs-title { display: flex; align-items: center; gap: 8px; font-size: 1.1rem; font-weight: 600; min-width: 0; }
  .labs-title .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--primary-color, #03a9f4); flex: none; }
  select, input {
    background: var(--secondary-background-color, #f2f2f2);
    color: var(--primary-text-color, #212121);
    border: 1px solid var(--divider-color, rgba(0,0,0,.12));
    border-radius: 8px; padding: 8px 10px; font-size: 1rem; min-height: 40px;
    box-sizing: border-box;
  }
  .labs-disclaimer {
    padding: 8px 10px; border-radius: 8px; font-size: .9rem;
    background: var(--warning-color, #ff9800); color: #fff;
  }
  .labs-error {
    padding: 8px 10px; border-radius: 8px; font-size: .9rem;
    background: var(--error-color, #db4437); color: #fff;
  }
  .labs-empty { color: var(--secondary-text-color); padding: 8px 0; }
  .labs-tabs { display: flex; flex-wrap: wrap; gap: 6px; }
  .labs-tab {
    border: 1px solid var(--divider-color, rgba(0,0,0,.12));
    background: var(--secondary-background-color, #f2f2f2);
    color: var(--primary-text-color, #212121);
    border-radius: 999px; padding: 6px 12px; font-size: .9rem; cursor: pointer;
  }
  .labs-tab.active { background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); border-color: transparent; }
  .labs-rows { display: flex; flex-direction: column; }
  .labs-row {
    display: grid; grid-template-columns: minmax(0, 2fr) auto auto auto minmax(0, 1fr);
    align-items: center; gap: 8px; padding: 8px 0;
    border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.08));
  }
  .labs-row:last-child { border-bottom: none; }
  .labs-name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .labs-subline { font-size: .8rem; line-height: 1.2; }
  .labs-value { font-variant-numeric: tabular-nums; white-space: nowrap; }
  .status.good { color: var(--success-color, #43a047); }
  .status.bad { color: var(--error-color, #db4437); }
  .muted { color: var(--secondary-text-color); }
  .labs-trend svg { display: block; }
  .labs-when { font-size: .8rem; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .labs-ref { text-decoration: none; margin-left: 4px; }
  .labs-entry {
    border-top: 1px solid var(--divider-color, rgba(0,0,0,.12));
    padding-top: 12px; display: flex; flex-direction: column; gap: 8px;
  }
  .labs-entry-title { font-weight: 600; }
  .labs-form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }
  .labs-form-grid label { display: flex; flex-direction: column; gap: 4px; font-size: .85rem; color: var(--secondary-text-color); }
  .labs-form-grid .wide { grid-column: 1 / -1; }
  .labs-report { border-top: 1px solid var(--divider-color, rgba(0,0,0,.08)); padding-top: 8px; }
  .labs-report summary { cursor: pointer; font-weight: 600; }
  .labs-report-fill { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
  .labs-report-rows { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
  .labs-report-row {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) auto;
    gap: 8px; align-items: center;
  }
  .labs-report-actions {
    display: flex; justify-content: space-between; gap: 8px;
    margin-top: 8px; flex-wrap: wrap;
  }
  .labs-report-discard { display: flex; justify-content: flex-end; margin-top: 8px; }
  .labs-save {
    align-self: flex-end; min-height: 40px; padding: 8px 18px; border: none; border-radius: 8px;
    background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff);
    font-size: 1rem; cursor: pointer;
  }
  .labs-save[disabled] { opacity: .6; cursor: default; }
  .editor { display: flex; flex-direction: column; gap: 16px; padding: 8px 0; }
  .editor-group { display: flex; flex-direction: column; gap: 6px; }
  .editor-group-title { font-weight: 600; }
  .editor-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .editor-check { display: flex; align-items: center; gap: 6px; font-size: .95rem; }
  .editor-hint { color: var(--secondary-text-color); font-size: .8rem; }
  .editor label { display: flex; flex-direction: column; gap: 4px; font-size: .9rem; }
`;

class HealthOMatLabsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._normalized = null;
    this._normalizedSource = null;
    this._hass = null;
    this._data = null;
    this._persons = null;
    this._activeEntry = "";
    this._activeCategory = "";
    this._draft = EMPTY_DRAFT();
    this._reportDraft = EMPTY_REPORT_DRAFT();
    this._reportOpen = false;
    this._fillNote = "";
    this._loading = false;
    this._saving = false;
    this._error = null;
    this._actionError = "";
    this._renderScheduled = false;
    this._listenersAttached = false;
    this._onClick = this._onClick.bind(this);
    this._onInput = this._onInput.bind(this);
    this._onChange = this._onChange.bind(this);
    this._onToggle = this._onToggle.bind(this);
  }

  /* ---- Lovelace card API -------------------------------------------------- */

  static getStubConfig() {
    return {
      entry_id: "",
      show_trend: true,
      allow_manual_entry: true,
      show_disclaimer: true,
    };
  }

  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("health-o-mat-labs-card: configuration is required");
    }
    this._config = config;
    this._normalized = null;
    this._normalizedSource = null;
    this._data = null;
    this._persons = null;
    this._activeEntry = "";
    this._activeCategory = "";
    this._draft = EMPTY_DRAFT();
    this._reportDraft = EMPTY_REPORT_DRAFT();
    this._reportOpen = false;
    this._fillNote = "";
    this._error = null;
    this._actionError = "";
    this._render();
    if (this._hass) this._loadData();
  }

  set hass(hass) {
    this._hass = hass;
    setCardLanguage(hass);
    if (!this._config) return;
    if (!this._data && !this._loading && !this._error) {
      this._loadData();
      return;
    }
    this._scheduleRender();
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return 6;
  }

  connectedCallback() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    if (this._listenersAttached) return;
    this.shadowRoot.addEventListener("click", this._onClick);
    this.shadowRoot.addEventListener("input", this._onInput);
    this.shadowRoot.addEventListener("change", this._onChange);
    // `toggle` bubbelt nicht — Capture-Phase faengt es am Shadow-Root ab.
    this.shadowRoot.addEventListener("toggle", this._onToggle, true);
    this._listenersAttached = true;
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._onClick);
    this.shadowRoot.removeEventListener("input", this._onInput);
    this.shadowRoot.removeEventListener("change", this._onChange);
    this.shadowRoot.removeEventListener("toggle", this._onToggle, true);
    this._listenersAttached = false;
  }

  _scheduleRender() {
    if (this._renderScheduled) return;
    this._renderScheduled = true;
    Promise.resolve().then(() => {
      this._renderScheduled = false;
      this._render();
    });
  }

  /* ---- Config ------------------------------------------------------------- */

  _configNorm() {
    if (!this._normalized || this._normalizedSource !== this._config) {
      this._normalized = normalizeCardConfig(this._config);
      this._normalizedSource = this._config;
    }
    return this._normalized;
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
        const result = await this._hass.callWS({ type: "health_o_mat/list_persons" });
        const allowed = filterPersons((result && result.persons) || [], cfg.personFilter);
        this._persons = allowed;
        if (!allowed.length) {
          this._error = cfg.personFilter.length
            ? "Keine Person passt zum konfigurierten Personen-Filter."
            : "Keine Person eingerichtet.";
          this._data = null;
          return;
        }
        if (cfg.personMode === "selector") {
          const known = entryId && allowed.some((person) => person.entry_id === entryId);
          const preferred =
            (cfg.defaultPerson &&
              allowed.find(
                (person) =>
                  person.entry_id === cfg.defaultPerson ||
                  person.person_slug === cfg.defaultPerson ||
                  person.display_name === cfg.defaultPerson
              )) ||
            null;
          entryId = known
            ? entryId
            : preferred
              ? preferred.entry_id
              : allowed[0].entry_id;
        } else {
          entryId = allowed[0].entry_id;
        }
      } else {
        this._persons = null;
      }
      if (entryId !== this._activeEntry) {
        this._activeCategory = "";
        this._draft = EMPTY_DRAFT();
        this._reportDraft = EMPTY_REPORT_DRAFT();
        this._reportOpen = false;
        this._fillNote = "";
      }
      this._activeEntry = entryId;
      if (!entryId) {
        this._error = "Keine Person eingerichtet.";
        this._data = null;
        return;
      }
      const data = await this._hass.callWS({
        type: "health_o_mat/panel_data",
        entry_id: entryId,
      });
      this._data = data || null;
      this._error = this._data ? null : "Keine Daten für diese Person.";
      if (silent && this._data) this._actionError = "";
    } catch (err) {
      this._error = err && err.message ? err.message : String(err);
      if (!silent) this._data = null;
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _labs() {
    return (this._data && this._data.labs) || { categories: [], markers: {} };
  }

  _markers() {
    return this._labs().markers || {};
  }

  _personName() {
    if (this._data && this._data.person) return String(this._data.person);
    const match = (this._persons || []).find(
      (person) => person && person.entry_id === this._activeEntry
    );
    return match ? String(match.display_name || "") : "";
  }

  /* ---- Category tabs ------------------------------------------------------ */

  _visibleCategories() {
    const cfg = this._configNorm();
    const markers = this._markers();
    const visible = (this._labs().categories || []).filter(
      (category) =>
        category &&
        category.key &&
        !category.hidden &&
        Object.values(markers).some(
          (marker) => marker && marker.category === category.key
        )
    );
    if (!cfg.showCategories.length) return visible;
    const configured = cfg.showCategories;
    return visible
      .filter((category) => configured.includes(category.key))
      .sort((a, b) => configured.indexOf(a.key) - configured.indexOf(b.key));
  }

  _activeCategoryKey() {
    const categories = this._visibleCategories();
    if (!categories.length) return "";
    if (
      this._activeCategory &&
      categories.some((category) => category.key === this._activeCategory)
    ) {
      return this._activeCategory;
    }
    return categories[0].key;
  }

  _categoryMarkers(categoryKey) {
    if (!categoryKey) return [];
    return Object.entries(this._markers())
      .filter(([, marker]) => marker && marker.category === categoryKey)
      .sort(([, a], [, b]) =>
        labDisplayName(a, "").localeCompare(labDisplayName(b, ""))
      );
  }

  _categoryTabs() {
    const categories = this._visibleCategories();
    if (!categories.length) {
      return `<div class="labs-empty">Keine Laborwert-Kategorie sichtbar.</div>`;
    }
    const active = this._activeCategoryKey();
    const tabs = categories
      .map(
        (category) =>
          `<button type="button" class="labs-tab${
            category.key === active ? " active" : ""
          }" data-action="lab-category" data-category="${escapeHtml(
            category.key
          )}" role="tab" aria-selected="${category.key === active}">${escapeHtml(
            labDisplayName(category, category.key)
          )}</button>`
      )
      .join("");
    return `<div class="labs-tabs" role="tablist">${tabs}</div>`;
  }

  _markerRow(key, marker, cfg) {
    const hasValue = marker.value != null && Number.isFinite(toNumber(marker.value, NaN));
    const valueText = hasValue
      ? `${formatLabValue(marker.value)}${
          marker.unit ? ` ${escapeHtml(marker.unit)}` : ""
        }`
      : `<span class="muted">—</span>`;
    const badge = hasValue ? labBadge(marker.in_range) : "";
    const trend = cfg.showTrend ? labSparkline(marker.history) : "";
    const when = hasValue ? formatRelativeTs(marker.ts) : "noch nie erfasst";
    const subline = labReportedSubline(marker);
    const refLink = reportRefHtml(marker.report_ref);
    const range = referenceText(marker);
    return `<div class="labs-row" data-marker="${escapeHtml(key)}"${
      range ? ` title="${escapeHtml(range)}"` : ""
    }>
      <div class="labs-marker">
        <div class="labs-name">${escapeHtml(labDisplayName(marker, key))} ${refLink}</div>
        ${subline}
      </div>
      <div class="labs-value">${valueText}</div>
      <div class="labs-badge">${badge}</div>
      <div class="labs-trend">${trend}</div>
      <div class="labs-when muted">${escapeHtml(when)}</div>
    </div>`;
  }

  _markerTable(cfg) {
    const categoryKey = this._activeCategoryKey();
    if (!categoryKey) return "";
    const rows = this._categoryMarkers(categoryKey);
    if (!rows.length) {
      return `<div class="labs-empty">Keine Marker in dieser Kategorie.</div>`;
    }
    return `<div class="labs-rows" role="tabpanel">${rows
      .map(([key, marker]) => this._markerRow(key, marker, cfg))
      .join("")}</div>`;
  }

  /* ---- Person picker ------------------------------------------------------ */

  _personPicker(cfg) {
    if (cfg.personMode !== "selector" || !this._persons || !this._persons.length) {
      return "";
    }
    const options = this._persons
      .map(
        (person) =>
          `<option value="${escapeHtml(person.entry_id)}"${
            person.entry_id === this._activeEntry ? " selected" : ""
          }>${escapeHtml(person.display_name || person.entry_id)}</option>`
      )
      .join("");
    return `<select data-role="lab-person" aria-label="Person">${options}</select>`;
  }

  /* ---- Manual entry ------------------------------------------------------- */

  _selectedMarkerKey() {
    const markers = this._markers();
    if (this._draft.marker && markers[this._draft.marker]) return this._draft.marker;
    const categoryRows = this._categoryMarkers(this._activeCategoryKey());
    if (categoryRows.length) return categoryRows[0][0];
    const entries = Object.keys(markers).sort((a, b) =>
      labDisplayName(markers[a], "").localeCompare(labDisplayName(markers[b], ""))
    );
    return entries.length ? entries[0] : "";
  }

  _entryForm() {
    const markers = this._markers();
    if (!Object.keys(markers).length) return "";
    const selectedKey = this._selectedMarkerKey();
    const selectedMarker = markers[selectedKey];
    // REQ-HOM-133 (#73): Bei Pflicht-Markern ist die Einheit kein optionales
    // Feld — das Placeholder sagt das, bevor der Server ablehnt.
    const unitPlaceholder =
      selectedMarker && selectedMarker.require_explicit_unit
        ? cardText("ui_panel_lab_unit_required")
        : selectedMarker && selectedMarker.unit
          ? `${selectedMarker.unit} (optional)`
          : "Einheit (optional)";
    return `<div class="labs-entry">
      <div class="labs-entry-title">Neuen Wert erfassen</div>
      <div class="labs-form-grid">
        <label>Marker
          <select data-field="lab-marker" aria-label="Marker">${labMarkerOptionsHtml(
            markers,
            selectedKey
          )}</select>
        </label>
        <label>Wert
          <input type="number" step="any" inputmode="decimal" data-field="lab-value" aria-label="Wert" value="${escapeHtml(
            this._draft.value
          )}" placeholder="Wert" />
        </label>
        <label>Einheit
          <input type="text" data-field="lab-unit" aria-label="Einheit" value="${escapeHtml(
            this._draft.unit
          )}" placeholder="${escapeHtml(unitPlaceholder)}" />
        </label>
        <label>Zeitpunkt
          <input type="datetime-local" data-field="lab-ts" aria-label="Zeitpunkt" value="${escapeHtml(
            this._draft.ts
          )}" />
        </label>
        <label class="wide">Bericht-Link/ID (optional)
          <input type="text" data-field="lab-report-ref" aria-label="Bericht-Link oder ID" value="${escapeHtml(
            this._draft.reportRef
          )}" placeholder="https://… oder Befund-ID" />
        </label>
      </div>
      <button type="button" class="labs-save" data-action="lab-save"${
        this._saving ? " disabled" : ""
      }>${this._saving ? "Speichern…" : "Speichern"}</button>
    </div>`;
  }

  _collectDraftFromDom() {
    const read = (field) => {
      const el = this.shadowRoot.querySelector(`[data-field="${field}"]`);
      return el && el.value != null ? String(el.value) : "";
    };
    const marker = read("lab-marker");
    if (marker) this._draft.marker = marker;
    this._draft.value = read("lab-value");
    this._draft.unit = read("lab-unit");
    this._draft.ts = read("lab-ts");
    this._draft.reportRef = read("lab-report-ref");
  }

  _updateUnitPlaceholder() {
    const markerEl = this.shadowRoot.querySelector('[data-field="lab-marker"]');
    const unitEl = this.shadowRoot.querySelector('[data-field="lab-unit"]');
    if (!markerEl || !unitEl) return;
    const key = markerEl.value != null ? String(markerEl.value) : "";
    const markers = this._markers();
    const selected = key && markers ? markers[key] : null;
    if (selected && selected.require_explicit_unit) {
      unitEl.placeholder = cardText("ui_panel_lab_unit_required");
      return;
    }
    const option = markerEl.options ? markerEl.options[markerEl.selectedIndex] : null;
    const unit = option && option.dataset ? option.dataset.unit || "" : "";
    unitEl.placeholder = unit ? `${unit} (optional)` : "Einheit (optional)";
  }

  _readEntryTs() {
    return this._validateTs(this._draft.ts);
  }

  async _saveValue() {
    if (this._saving) return;
    this._collectDraftFromDom();
    const entryId = this._activeEntry;
    const markerKey = this._draft.marker;
    const rawValue = String(this._draft.value || "").trim().replace(",", ".");
    if (!entryId) {
      this._actionError = "Keine Person ausgewählt.";
      this._render();
      return;
    }
    if (!markerKey) {
      this._actionError = "Bitte einen Marker auswählen.";
      this._render();
      return;
    }
    if (!/^-?\d+(\.\d+)?$/.test(rawValue)) {
      this._actionError = "Bitte einen gültigen Wert eingeben.";
      this._render();
      return;
    }
    const ts = this._readEntryTs();
    if (ts.error) {
      this._actionError = ts.error;
      this._render();
      return;
    }
    const payload = {
      type: "health_o_mat/add_lab_value",
      entry_id: entryId,
      marker: markerKey,
      value: Number(rawValue),
    };
    if (String(this._draft.unit || "").trim()) {
      payload.unit = String(this._draft.unit).trim();
    }
    if (ts.iso) payload.ts = ts.iso;
    if (String(this._draft.reportRef || "").trim()) {
      payload.report_ref = String(this._draft.reportRef).trim();
    }
    this._saving = true;
    this._actionError = "";
    this._render();
    try {
      await this._hass.connection.sendMessagePromise(payload);
      this._actionError = "";
      this._draft.value = "";
      this._draft.ts = "";
      this._draft.reportRef = "";
      await this._loadData(true);
    } catch (err) {
      this._actionError = errorMessage(err);
    } finally {
      this._saving = false;
      this._render();
    }
  }

  /* ---- Mehrzeilen-Dialog: Laborbericht (REQ-HOM-123) ---------------------- */

  _reportMarkerOptions(markers, selectedKey) {
    const placeholder = selectedKey
      ? ""
      : '<option value="" selected>— bitte wählen —</option>';
    return `${placeholder}${labMarkerOptionsHtml(markers, selectedKey)}`;
  }

  _unitOptions(marker, selectedUnit) {
    const canonical = (marker && marker.unit) || "";
    const altUnits = Object.keys((marker && marker.alt_units) || {});
    const known = [canonical, ...altUnits].filter(
      (unit, index, all) => unit && all.indexOf(unit) === index
    );
    const current = selectedUnit
      ? known.includes(selectedUnit)
        ? selectedUnit
        : "__custom__"
      : canonical;
    const options = known
      .map(
        (unit) =>
          `<option value="${escapeHtml(unit)}"${
            unit === current ? " selected" : ""
          }>${escapeHtml(unit)}</option>`
      )
      .join("");
    // REQ-HOM-133 (#73): Pflicht-Marker warnen im Dropdown, bevor der Server
    // `unit_required` meldet. Deaktivierte Hinweiszeile — die kanonische
    // Einheit bleibt vorausgewählt und damit ein gültiger Wert.
    const requiredHint =
      marker && marker.require_explicit_unit
        ? `<option value="" disabled>${escapeHtml(
            cardText("ui_panel_lab_unit_required")
          )}</option>`
        : "";
    return `${requiredHint}${options}<option value="__custom__"${
      current === "__custom__" ? " selected" : ""
    }>Andere …</option>`;
  }

  _reportRow(row, index, markers) {
    const marker = markers[row.marker];
    const disabled = this._saving ? " disabled" : "";
    return `<div class="labs-report-row" data-role="lab-report-row">
      <select data-field="lab-report-marker-${index}" aria-label="Marker"${disabled}>${this._reportMarkerOptions(
        markers,
        row.marker
      )}</select>
      <input type="number" step="any" inputmode="decimal" data-field="lab-report-value-${index}"
        aria-label="Wert" value="${escapeHtml(row.value)}" placeholder="Wert"${disabled} />
      <select data-field="lab-report-unit-pick-${index}" aria-label="Einheit"${disabled}>${this._unitOptions(
        marker,
        row.unit
      )}</select>
      <input type="text" data-field="lab-report-unit-${index}" aria-label="Einheit (Freitext)"
        value="${escapeHtml(row.unit)}" placeholder="${escapeHtml(
          (marker && marker.unit) || "Einheit"
        )}" autocomplete="off"${disabled} />
      <button type="button" class="labs-tab" data-action="lab-report-remove" data-index="${index}"
        aria-label="Zeile entfernen"${disabled}>✕</button>
    </div>`;
  }

  _reportForm() {
    const markers = this._markers();
    if (!Object.keys(markers).length) return "";
    const draft = this._reportDraft;
    const atLimit = draft.rows.length >= LAB_REPORT_MAX_ROWS_UI;
    const disabled = this._saving ? " disabled" : "";
    const addDisabled = this._saving || atLimit ? " disabled" : "";
    const rows = draft.rows
      .map((row, index) => this._reportRow(row, index, markers))
      .join("");
    const note = atLimit
      ? `Höchstens ${LAB_REPORT_MAX_ROWS_UI} Zeilen pro Bericht.`
      : this._fillNote;
    const noteHtml = note ? `<div class="labs-empty">${escapeHtml(note)}</div>` : "";
    return `<details class="labs-report">
      <summary>Laborbericht erfassen</summary>
      <div class="labs-report-fill">
        <button type="button" class="labs-tab" data-action="lab-report-fill-visible"${disabled}>Alle sichtbaren Marker anlegen</button>
        <button type="button" class="labs-tab" data-action="lab-report-fill-last"${disabled}>Zuletzt verwendete Marker anlegen</button>
      </div>
      <div class="labs-form-grid">
        <label>Zeitpunkt
          <input type="datetime-local" data-field="lab-report-ts" aria-label="Zeitpunkt"
            value="${escapeHtml(draft.ts)}" />
        </label>
        <label class="wide">Bericht-Link/ID (optional)
          <input type="text" data-field="lab-report-ref" aria-label="Bericht-Link oder ID"
            value="${escapeHtml(draft.reportRef)}" placeholder="https://… oder Befund-ID"
            autocomplete="off" />
        </label>
      </div>
      <div class="labs-report-rows">${rows}</div>
      ${noteHtml}
      <div class="labs-report-actions">
        <button type="button" class="labs-tab" data-action="lab-report-add"${addDisabled}>＋ Zeile</button>
        <button type="button" class="labs-save" data-action="lab-report-save"${disabled}>${
          this._saving ? "Speichern…" : "Bericht speichern"
        }</button>
      </div>
    </details>`;
  }

  _collectReportDraftFromDom() {
    const read = (field) => {
      const el = this.shadowRoot.querySelector(`[data-field="${field}"]`);
      return el && el.value != null ? String(el.value) : "";
    };
    this._reportDraft.ts = read("lab-report-ts");
    this._reportDraft.reportRef = read("lab-report-ref");
    this._reportDraft.rows = this._reportDraft.rows.map((_row, index) => ({
      marker: read(`lab-report-marker-${index}`),
      value: read(`lab-report-value-${index}`),
      unit: read(`lab-report-unit-${index}`),
    }));
  }

  _fillReportDraft(mode) {
    this._collectReportDraftFromDom();
    const markers = this._markers();
    let keys = [];
    if (mode === "visible") {
      // „sichtbar" = was die Karte tatsächlich als Kategorie zeigt (hidden-Flag
      // UND show_categories-Konfiguration).
      const visible = new Set(this._visibleCategories().map((category) => category.key));
      keys = Object.keys(markers).filter((key) => visible.has(markers[key].category));
    } else {
      const last = this._labs().last_report || {};
      keys = (Array.isArray(last.marker_keys) ? last.marker_keys : []).filter(
        (key) => markers[key]
      );
    }
    const used = new Set(this._reportDraft.rows.map((row) => row.marker).filter(Boolean));
    let limitHit = false;
    for (const key of keys) {
      if (used.has(key)) continue;
      const empty = this._reportDraft.rows.find(
        (row) => !row.marker && !row.value && !row.unit
      );
      if (empty) {
        empty.marker = key;
      } else if (this._reportDraft.rows.length < LAB_REPORT_MAX_ROWS_UI) {
        this._reportDraft.rows.push({ marker: key, value: "", unit: "" });
      } else {
        limitHit = true;
        break;
      }
      used.add(key);
    }
    this._fillNote = limitHit
      ? `Höchstens ${LAB_REPORT_MAX_ROWS_UI} Zeilen pro Bericht.`
      : "";
    this._render();
  }

  _addReportRow() {
    if (this._reportDraft.rows.length >= LAB_REPORT_MAX_ROWS_UI) return;
    this._collectReportDraftFromDom();
    this._reportDraft.rows.push(EMPTY_REPORT_ROW());
    this._render();
  }

  _removeReportRow(index) {
    if (!Number.isInteger(index) || this._reportDraft.rows.length <= 1) return;
    this._collectReportDraftFromDom();
    this._reportDraft.rows.splice(index, 1);
    this._render();
  }

  _onReportField(field, value) {
    if (field === "lab-report-ts") {
      this._reportDraft.ts = value;
      return;
    }
    if (field === "lab-report-ref") {
      this._reportDraft.reportRef = value;
      return;
    }
    const match = /^lab-report-(marker|value|unit)-(\d+)$/.exec(field);
    if (!match) return;
    const row = this._reportDraft.rows[Number(match[2])];
    if (row) row[match[1]] = value;
  }

  _onUnitPick(index, value) {
    const row = this._reportDraft.rows[index];
    if (!row) return;
    row.unit = value === "__custom__" ? "" : value;
    const input = this.shadowRoot.querySelector(`[data-field="lab-report-unit-${index}"]`);
    if (input) input.value = row.unit;
  }

  _validateTs(rawInput) {
    const raw = String(rawInput || "").trim();
    if (!raw) return { iso: "" };
    const parsed = new Date(raw);
    if (!Number.isFinite(parsed.getTime())) {
      return { error: "Ungültiger Zeitpunkt — bitte Datum und Uhrzeit prüfen." };
    }
    if (parsed.getTime() > Date.now() + TS_FUTURE_TOLERANCE_MS) {
      return {
        error:
          "Der Zeitpunkt liegt in der Zukunft (erlaubt sind bis zu 5 Minuten Toleranz).",
      };
    }
    return { iso: parsed.toISOString() };
  }

  _readReportTs() {
    return this._validateTs(this._reportDraft.ts);
  }

  async _saveReport() {
    if (this._saving) return;
    this._collectReportDraftFromDom();
    const entryId = this._activeEntry;
    if (!entryId) {
      this._actionError = "Keine Person ausgewählt.";
      this._render();
      return;
    }
    const ts = this._readReportTs();
    if (ts.error) {
      this._actionError = ts.error;
      this._render();
      return;
    }
    const values = [];
    for (const row of this._reportDraft.rows) {
      const marker = String(row.marker || "").trim();
      const rawValue = String(row.value || "").trim().replace(",", ".");
      const unit = String(row.unit || "").trim();
      if (!marker && !rawValue && !unit) continue;
      if (!marker) {
        this._actionError = "Bitte für jede befüllte Zeile einen Marker auswählen.";
        this._render();
        return;
      }
      if (!/^-?\d+(\.\d+)?$/.test(rawValue)) {
        this._actionError = "Bitte für jede befüllte Zeile einen gültigen Wert eingeben.";
        this._render();
        return;
      }
      values.push(
        unit
          ? { marker, value: Number(rawValue), unit }
          : { marker, value: Number(rawValue) }
      );
    }
    if (!values.length) {
      this._actionError = "Bitte mindestens einen Wert erfassen.";
      this._render();
      return;
    }
    const payload = { type: "health_o_mat/add_lab_report", entry_id: entryId, values };
    if (ts.iso) payload.ts = ts.iso;
    if (String(this._reportDraft.reportRef || "").trim()) {
      payload.report_ref = String(this._reportDraft.reportRef).trim();
    }
    this._saving = true;
    this._actionError = "";
    this._render();
    try {
      const result = await this._hass.connection.sendMessagePromise(payload);
      const failure = resultError(result);
      if (failure) {
        this._actionError = failure;
        return;
      }
      this._actionError = "";
      // Bericht-Kontext (ts/reportRef) bleibt für Nachtrag-Korrekturen stehen
      // (§6.4) — geleert werden nur Wert-Felder und die Zeilenliste.
      this._reportDraft = { ...this._reportDraft, rows: [EMPTY_REPORT_ROW()] };
      // Der Dialog startet nach dem Absenden wieder im Startzustand (zugeklappt).
      this._reportOpen = false;
      this._fillNote = "";
      await this._loadData(true);
    } catch (err) {
      this._actionError = reportErrorMessage(err);
    } finally {
      this._saving = false;
      this._render();
    }
  }

  _discardReportBar() {
    const last = this._labs().last_report;
    if (!last || !last.ts) return "";
    const count = Array.isArray(last.marker_keys) ? last.marker_keys.length : 0;
    return `<div class="labs-report-discard">
      <button type="button" class="labs-tab" data-action="lab-report-discard"${
        this._saving ? " disabled" : ""
      }>Diesen Bericht verwerfen (${count})</button>
    </div>`;
  }

  async _discardReport() {
    if (this._saving) return;
    const last = this._labs().last_report;
    if (!last || !last.ts) return;
    const count = Array.isArray(last.marker_keys) ? last.marker_keys.length : 0;
    const confirmed =
      typeof window !== "undefined" && typeof window.confirm === "function"
        ? window.confirm(`Diesen Bericht mit ${count} Werten verwerfen?`)
        : true;
    if (!confirmed) return;
    if (!this._activeEntry) return;
    const payload = {
      type: "health_o_mat/remove_lab_report",
      entry_id: this._activeEntry,
      ts: last.ts,
    };
    if (last.report_ref) payload.report_ref = last.report_ref;
    this._saving = true;
    this._actionError = "";
    this._render();
    try {
      const result = await this._hass.connection.sendMessagePromise(payload);
      const failure = resultError(result);
      if (failure) {
        this._actionError = failure;
        return;
      }
      await this._loadData(true);
    } catch (err) {
      this._actionError = reportErrorMessage(err);
    } finally {
      this._saving = false;
      this._render();
    }
  }

  /* ---- Events ------------------------------------------------------------- */

  _onClick(ev) {
    const el = ev.target && ev.target.closest ? ev.target.closest("[data-action]") : null;
    if (!el) return;
    const action = el.getAttribute("data-action");
    if (action === "lab-category") {
      const key = el.getAttribute("data-category") || "";
      if (key) {
        this._activeCategory = key;
        this._render();
      }
      return;
    }
    if (action === "lab-report-add") {
      this._addReportRow();
      return;
    }
    if (action === "lab-report-remove") {
      this._removeReportRow(Number(el.getAttribute("data-index")));
      return;
    }
    if (action === "lab-report-fill-visible") {
      this._fillReportDraft("visible");
      return;
    }
    if (action === "lab-report-fill-last") {
      this._fillReportDraft("last");
      return;
    }
    if (action === "lab-report-discard") {
      this._discardReport();
      return;
    }
    if (action === "lab-report-save") this._saveReport();
    if (action === "lab-save") this._saveValue();
  }

  /* Offen-Zustand des Bericht-Dialogs merken: strukturelle Aenderungen (Zeile,
   * Marker, Einheit) rendern den Shadow-Root neu — ohne diesen Zustand faellt
   * das `<details>` bei jedem Klick zu (E2E-Befund Batch-Dialog). */
  _onToggle(ev) {
    const el = ev.target;
    if (!el || typeof el.matches !== "function") return;
    if (!el.matches("details.labs-report")) return;
    this._reportOpen = el.open === true;
  }

  _onInput(ev) {
    const el = ev.target;
    if (!el || !el.getAttribute) return;
    const field = el.getAttribute("data-field");
    if (field && field.startsWith("lab-report-")) {
      this._onReportField(field, String(el.value || ""));
      return;
    }
    if (field === "lab-value") this._draft.value = String(el.value || "");
    else if (field === "lab-unit") this._draft.unit = String(el.value || "");
    else if (field === "lab-report-ref") this._draft.reportRef = String(el.value || "");
  }

  _onChange(ev) {
    const el = ev.target;
    if (!el || !el.getAttribute) return;
    const role = el.getAttribute("data-role");
    if (role === "lab-person") {
      this._selectPerson(String(el.value || ""));
      return;
    }
    const field = el.getAttribute("data-field");
    const markerMatch = /^lab-report-marker-(\d+)$/.exec(field || "");
    if (markerMatch) {
      this._collectReportDraftFromDom();
      const row = this._reportDraft.rows[Number(markerMatch[1])];
      if (row) {
        row.marker = String(el.value || "");
        row.unit = ""; // Einheiten-Dropdown hängt am Marker
      }
      this._render();
      return;
    }
    const unitPickMatch = /^lab-report-unit-pick-(\d+)$/.exec(field || "");
    if (unitPickMatch) {
      this._onUnitPick(Number(unitPickMatch[1]), String(el.value || ""));
      return;
    }
    if (field && field.startsWith("lab-report-")) {
      this._onReportField(field, String(el.value || ""));
      return;
    }
    if (field === "lab-marker") {
      this._draft.marker = String(el.value || "");
      this._updateUnitPlaceholder();
    } else if (field === "lab-value") this._draft.value = String(el.value || "");
    else if (field === "lab-unit") this._draft.unit = String(el.value || "");
    else if (field === "lab-ts") this._draft.ts = String(el.value || "");
    else if (field === "lab-report-ref") this._draft.reportRef = String(el.value || "");
  }

  _selectPerson(entryId) {
    if (!entryId || entryId === this._activeEntry) return;
    this._activeEntry = entryId;
    this._data = null;
    this._error = null;
    this._actionError = "";
    this._activeCategory = "";
    this._draft = EMPTY_DRAFT();
    this._reportDraft = EMPTY_REPORT_DRAFT();
    this._fillNote = "";
    this._loadData();
  }

  /* ---- Render ------------------------------------------------------------- */

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const cfg = this._configNorm();
    const disclaimer = cfg.showDisclaimer
      ? `<div class="labs-disclaimer" role="note">${escapeHtml(
          cardText("ui_card_lab_disclaimer")
        )}</div>`
      : "";
    const errorBanner = this._error
      ? `<div class="labs-error" role="alert">⚠️ ${escapeHtml(this._error)}</div>`
      : "";
    const actionError = this._actionError
      ? `<div class="labs-error" role="alert">⚠️ ${escapeHtml(this._actionError)}</div>`
      : "";
    const loading = this._loading ? `<div class="labs-empty">Laborwerte werden geladen…</div>` : "";
    const hasData = !this._loading && !!this._data;
    const body = hasData ? `${this._categoryTabs()}${this._markerTable(cfg)}` : "";
    const entryForm = hasData && cfg.allowManualEntry ? this._entryForm() : "";
    const reportForm = hasData && cfg.allowManualEntry ? this._reportForm() : "";
    const name = this._personName();
    const personSuffix = name ? ` — <span class="name">${escapeHtml(name)}</span>` : "";
    this.shadowRoot.innerHTML = `
      <style>${CARD_CSS}</style>
      <ha-card>
        <div class="labs-card">
          <div class="labs-head">
            <div class="labs-title"><span class="dot"></span><span>Laborwerte</span>${personSuffix}</div>
            ${this._personPicker(cfg)}
          </div>
          ${disclaimer}
          ${errorBanner}
          ${actionError}
          ${loading}
          ${body}
          ${this._discardReportBar()}
          ${entryForm}
          ${reportForm}
        </div>
      </ha-card>
    `;
    // Offen-Zustand nach dem Re-Render wiederherstellen: innerHTML ersetzt das
    // `<details>`-Element, der gemerkte Zustand haelt den Dialog offen.
    const reportEl = this.shadowRoot.querySelector("details.labs-report");
    if (reportEl) reportEl.open = this._reportOpen === true;
  }
}

/* ---- Visual editor -------------------------------------------------------- */

class HealthOMatLabsCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._persons = null;
    this._categories = null;
    this._categoriesEntry = "";
    this._personFilterEditing = false;
    this._loading = false;
    this._listenersAttached = false;
    this._onValueChange = this._onValueChange.bind(this);
  }

  setConfig(config) {
    const next = config || {};
    const previous = this._config && this._config.entry_id ? String(this._config.entry_id) : "";
    const current = next.entry_id ? String(next.entry_id) : "";
    this._config = next;
    if (previous !== current) {
      this._categories = null;
      this._categoriesEntry = "";
      this._maybeLoadCategories();
    }
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    setCardLanguage(hass);
    if (first && hass) {
      if (this._persons === null) this._loadPersons();
      this._maybeLoadCategories();
    }
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    if (this._listenersAttached) return;
    this.shadowRoot.addEventListener("input", this._onValueChange);
    this.shadowRoot.addEventListener("change", this._onValueChange);
    this._listenersAttached = true;
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("input", this._onValueChange);
    this.shadowRoot.removeEventListener("change", this._onValueChange);
    this._listenersAttached = false;
  }

  async _loadPersons() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      const result = await this._hass.callWS({ type: "health_o_mat/list_persons" });
      this._persons = (result && result.persons) || [];
    } catch (_error) {
      // Editor bleibt bedienbar: freie Eingabe der entry_id ist der Fallback.
      this._persons = [];
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _entryId() {
    return this._config && this._config.entry_id ? String(this._config.entry_id) : "";
  }

  _maybeLoadCategories() {
    const entryId = this._entryId();
    if (!this._hass || !entryId) return;
    if (this._categoriesEntry === entryId) return;
    this._loadCategories(entryId);
  }

  async _loadCategories(entryId) {
    if (!this._hass || !entryId) return;
    this._categoriesEntry = entryId;
    try {
      const result = await this._hass.callWS({
        type: "health_o_mat/panel_data",
        entry_id: entryId,
      });
      if (this._categoriesEntry !== entryId) return;
      const categories =
        (result && result.labs && result.labs.categories) || [];
      this._categories = categories.filter((category) => category && !category.hidden);
    } catch (_error) {
      if (this._categoriesEntry !== entryId) return;
      this._categories = [];
    } finally {
      if (this._categoriesEntry === entryId) this._render();
    }
  }

  _setConfig(next, rerender) {
    this._config = next;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: next },
        bubbles: true,
        composed: true,
      })
    );
    if (rerender) this._render();
  }

  _onValueChange(ev) {
    const target = ev.target;
    if (!target || !target.getAttribute) return;
    const role = target.getAttribute("data-role");
    if (role === "category") {
      if (ev.type !== "change") return;
      this._toggleCategory(target.getAttribute("data-key") || "", target.checked === true);
      return;
    }
    if (role === "categories-all") {
      if (ev.type !== "change") return;
      const next = Object.assign({}, this._config);
      delete next.show_categories;
      this._setConfig(next, true);
      return;
    }
    if (role === "person-filter") {
      if (ev.type !== "change") return;
      this._togglePersonFilter(target.getAttribute("data-key") || "", target.checked === true);
      return;
    }
    if (role === "person-filter-all") {
      if (ev.type !== "change") return;
      const next = Object.assign({}, this._config);
      this._personFilterEditing = target.checked !== true;
      delete next.person_filter;
      this._setConfig(next, true);
      return;
    }
    const key = target.getAttribute("data-key");
    if (!key) return;
    if (target.type === "checkbox") {
      if (ev.type !== "change") return;
      this._toggleFlag(key, target.checked === true);
      return;
    }
    // Freitext/Selects erst bei `change` uebernehmen (kein Rebuild pro Tastendruck).
    if (ev.type !== "change") return;
    const next = Object.assign({}, this._config);
    if (key === "person_mode") {
      const mode = String(target.value || "");
      this._personFilterEditing = false;
      if (mode === "selector") {
        delete next.entry_id;
        this._categories = null;
        this._categoriesEntry = "";
      } else if (!next.entry_id && this._persons && this._persons.length) {
        next.entry_id = this._persons[0].entry_id;
        this._config = next;
        this._maybeLoadCategories();
      }
      this._setConfig(next, true);
      return;
    }
    next[key] = target.value;
    if (key === "entry_id") {
      this._categories = null;
      this._categoriesEntry = "";
      this._config = next;
      this._maybeLoadCategories();
    }
    this._setConfig(next, key === "entry_id");
  }

  _toggleFlag(key, checked) {
    const next = Object.assign({}, this._config);
    // `true` ist der Default — nur `false` explizit speichern.
    if (checked) delete next[key];
    else next[key] = false;
    this._setConfig(next, true);
  }

  _personFilterValues() {
    return normalizeStringList(this._config.person_filter);
  }

  _togglePersonFilter(key, checked) {
    if (!key) return;
    const allKeys = (this._persons || []).map((person) => person.entry_id).filter(Boolean);
    if (!allKeys.length) return;
    let selected = this._personFilterValues();
    if (checked) {
      if (!selected.includes(key)) selected.push(key);
    } else {
      selected = selected.filter((item) => item !== key);
    }
    this._personFilterEditing = false;
    const next = Object.assign({}, this._config);
    const ordered = allKeys.filter((item) => selected.includes(item));
    if (!ordered.length || ordered.length === allKeys.length) {
      delete next.person_filter;
    } else {
      next.person_filter = ordered;
    }
    this._setConfig(next, true);
  }

  _categoryKeys() {
    return (this._categories || []).map((category) => category.key).filter(Boolean);
  }

  _selectedCategoryKeys() {
    const allKeys = this._categoryKeys();
    const configured = normalizeStringList(this._config.show_categories);
    if (!configured.length) return allKeys;
    const known = configured.filter((key) => allKeys.includes(key));
    return known.length ? known : allKeys;
  }

  _toggleCategory(key, checked) {
    if (!key) return;
    const allKeys = this._categoryKeys();
    if (!allKeys.length) return;
    let selected = this._selectedCategoryKeys();
    if (checked) {
      if (!selected.includes(key)) selected.push(key);
    } else {
      selected = selected.filter((item) => item !== key);
    }
    const next = Object.assign({}, this._config);
    const ordered = allKeys.filter((item) => selected.includes(item));
    if (!ordered.length || ordered.length === allKeys.length) {
      delete next.show_categories;
    } else {
      next.show_categories = ordered;
    }
    this._setConfig(next, true);
  }

  _personOptions(current) {
    const options = [];
    options.push(
      `<option value=""${current ? "" : " selected"}>Automatisch (Personenauswahl in der Karte)</option>`
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
    if (!hasCurrent) {
      options.push(
        `<option value="${escapeHtml(current)}" selected>${escapeHtml(current)}</option>`
      );
    }
    return options.join("");
  }

  _checkbox(key, label) {
    const checked =
      Object.prototype.hasOwnProperty.call(this._config, key) &&
      toBool(this._config[key], true) === false
        ? ""
        : " checked";
    return `<label class="editor-check">
      <input type="checkbox" data-key="${key}"${checked} />
      <span>${escapeHtml(label)}</span>
    </label>`;
  }

  _personSection() {
    const current = this._entryId();
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
            <div class="editor-hint">„Alle Personen“ abwählen, um einzelne Personen auszuwählen.</div>`
          : `<div class="editor-hint">Personenliste wird geladen…</div>`;
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

  _categoriesSection() {
    const head = `<div class="editor-group-title">Kategorien</div>`;
    if (!this._entryId()) {
      return `<div class="editor-group">${head}
        <div class="editor-hint">Person wählen, um die Kategorien zu laden. Ohne eigene Auswahl erscheinen alle aktiven Kategorien.</div>
      </div>`;
    }
    if (this._categories === null) {
      return `<div class="editor-group">${head}
        <div class="editor-hint">Kategorien werden geladen…</div>
      </div>`;
    }
    if (!this._categories.length) {
      return `<div class="editor-group">${head}
        <div class="editor-hint">Keine aktive Laborwert-Kategorie für diese Person.</div>
      </div>`;
    }
    const selected = this._selectedCategoryKeys();
    const allSelected = selected.length === this._categories.length;
    const rows = this._categories
      .map(
        (category) => `<label class="editor-check">
          <input type="checkbox" data-role="category" data-key="${escapeHtml(
            category.key
          )}"${selected.includes(category.key) ? " checked" : ""} />
          <span>${escapeHtml(labDisplayName(category, category.key))}</span>
        </label>`
      )
      .join("");
    return `<div class="editor-group">${head}
      <label class="editor-check">
        <input type="checkbox" data-role="categories-all"${allSelected ? " checked" : ""} />
        <span>Alle aktiven Kategorien</span>
      </label>
      ${rows}
      <div class="editor-hint">Tab-Reihenfolge folgt der Katalog-Reihenfolge.</div>
    </div>`;
  }

  _render() {
    if (!this.shadowRoot) return;
    const current = this._entryId();
    const mode = String(this._config.person_mode || (current ? "fixed" : "selector"));
    const personPicker =
      mode === "fixed"
        ? `<label>Feste Person
            <select data-key="entry_id">${this._personOptions(current)}</select>
          </label>`
        : `<div class="editor-hint">Dropdown-Modus: die angezeigten Personen werden im Abschnitt „Personen-Bindung“ gefiltert.</div>`;
    this.shadowRoot.innerHTML = `
      <style>${CARD_CSS}</style>
      <div class="editor">
        ${personPicker}
        <label>Default-Person
          <input type="text" data-key="default_person" value="${escapeHtml(
            this._config.default_person || ""
          )}" placeholder="entry_id (optional)" />
        </label>
        ${this._personSection()}
        ${this._categoriesSection()}
        <div class="editor-group">
          <div class="editor-group-title">Anzeige</div>
          ${this._checkbox("show_trend", "Sparkline anzeigen")}
          ${this._checkbox("allow_manual_entry", "Manuelle Eingabe erlauben")}
          ${this._checkbox("show_disclaimer", "Medizin-Hinweis anzeigen")}
        </div>
      </div>
    `;
  }
}

if (!customElements.get(CARD_TAG)) {
  customElements.define("health-o-mat-labs-card", HealthOMatLabsCard);
}
if (!customElements.get(EDITOR_TAG)) {
  customElements.define("health-o-mat-labs-card-editor", HealthOMatLabsCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card && card.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "Health-O-Mat Laborwerte",
    description: "Laborwerte (Blutwerte) je Person, kategorisiert mit Referenzbereichen.",
    preview: false,
    documentationURL: "https://github.com/Popoboxxo/ha-health-o-mat",
  });
}

console.info(
  `%c HEALTH-O-MAT-LABS-CARD %c v${CARD_VERSION} `,
  "color:#fff;background:#03a9f4;font-weight:700;border-radius:3px 0 0 3px",
  "color:#03a9f4;background:#fff;font-weight:700;border-radius:0 3px 3px 0"
);

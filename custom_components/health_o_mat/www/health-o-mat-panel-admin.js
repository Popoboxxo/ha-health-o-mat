/**
 * Health-O-Mat — Panel admin module.
 *
 * Admin-only settings view (per-person settings form, export) plus the D7
 * person-management surface: list persons, add a person (HA config flow),
 * delete a person with double confirmation, and trigger a backup.
 *
 * Pure rendering + payload collection helpers; the WebSocket calls themselves
 * live in the entry module (which owns the `hass` object). The server gates
 * every command here as admin as well — this view is only rendered for admins,
 * but that UI gate is never the security boundary.
 *
 * Import specifier carries the integration version (cache-buster, see base).
 */

import {
  SETTINGS_LIMITS,
  SETTINGS_FALLBACKS,
  EXPORT_DATASETS,
  WELLBEING_STATES,
  escapeHtml,
  attrValue,
  datasetLabel,
  normalizeAreas,
  personSlug,
  messageHtml,
} from "./health-o-mat-panel-base.js?v=0.12.0";

/* ---- Settings view ------------------------------------------------------- */

export function renderSettings(panel) {
  const head = `<div class="person-head"><span class="dot"></span><span>Einstellungen</span></div>`;
  const persons = panel._persons || [];
  const personsCard = personsPanel(panel);
  if (!persons.length) {
    return `${head}${personsCard}${messageHtml("Keine Person eingerichtet.", false)}`;
  }
  // Keep the selection in sync with the rendered person list.
  let entryId = panel._settingsEntry;
  if (!entryId || !persons.some((p) => p.entry_id === entryId)) {
    entryId = panel._selectedEntry && persons.some((p) => p.entry_id === panel._selectedEntry)
      ? panel._selectedEntry
      : persons[0].entry_id;
    panel._settingsEntry = entryId;
  }

  const selector = persons.length > 1
    ? `<div class="card">
        <label class="field">Person
          <select data-action="settings-person">${settingsPersonOptions(panel, entryId)}</select>
        </label>
      </div>`
    : "";

  const settings = panel._settings[entryId];
  const loadError = panel._settingsErrors[entryId];
  if (!settings) {
    const inner = loadError
      ? messageHtml(loadError, true)
      : messageHtml("Lade Einstellungen\u2026", false);
    return `${head}${personsCard}${selector}${inner}`;
  }
  return `${head}${personsCard}${selector}${settingsForm(panel, settings, entryId, loadError)}`;
}

function settingsPersonOptions(panel, entryId) {
  return (panel._persons || [])
    .map(
      (p) =>
        `<option value="${escapeHtml(p.entry_id)}"${p.entry_id === entryId ? " selected" : ""}>${escapeHtml(p.display_name)}</option>`
    )
    .join("");
}

function settingsForm(panel, settings, entryId, loadError) {
  const s = settings || {};
  const goal = s.daily_goal_ml == null ? SETTINGS_FALLBACKS.daily_goal_ml : s.daily_goal_ml;
  const reset = s.daily_reset_hour == null ? SETTINGS_FALLBACKS.daily_reset_hour : s.daily_reset_hour;
  const sys = s.sys_threshold == null ? SETTINGS_FALLBACKS.sys_threshold : s.sys_threshold;
  const dia = s.dia_threshold == null ? SETTINGS_FALLBACKS.dia_threshold : s.dia_threshold;
  const retention = s.retention_months == null ? SETTINGS_FALLBACKS.retention_months : s.retention_months;
  const sidebar = s.enable_sidebar_panel === true;
  const lexicon = s.drink_lexicon == null ? "" : String(s.drink_lexicon);
  const display = s.person_display == null ? "" : String(s.person_display);
  const areas = normalizeAreas(s.areas);
  const images =
    s.wellbeing_images && typeof s.wellbeing_images === "object" ? s.wellbeing_images : {};

  const banner = loadError
    ? `<div class="banner" role="alert">\u26A0\uFE0F ${escapeHtml(loadError)}</div>`
    : "";

  return `<form class="settings-form" data-form="settings">
      ${banner}
      <div class="card">
        <div class="card-title">Allgemein</div>
        <div class="settings-grid">
          <label class="field">Tagesziel (ml)
            <input type="number" inputmode="numeric" data-field="daily_goal_ml"
              min="${SETTINGS_LIMITS.goalMin}" max="${SETTINGS_LIMITS.goalMax}"
              value="${attrValue(goal)}" />
          </label>
          <label class="field">Tages-Reset (Stunde, 0\u201323)
            <input type="number" inputmode="numeric" data-field="daily_reset_hour"
              min="${SETTINGS_LIMITS.resetMin}" max="${SETTINGS_LIMITS.resetMax}"
              value="${attrValue(reset)}" />
          </label>
          <label class="field">Anzeigename
            <input type="text" data-field="person_display" autocomplete="off"
              value="${attrValue(display)}" />
          </label>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Bereiche</div>
        <div class="muted">Abgew\u00E4hlte Bereiche werden in \u00DCbersicht und Detail ausgeblendet.</div>
        <label class="check">
          <input type="checkbox" data-field="area-drink"${areas.drink ? " checked" : ""} />
          <span>Trinken</span>
        </label>
        <label class="check">
          <input type="checkbox" data-field="area-bp"${areas.bp ? " checked" : ""} />
          <span>Blutdruck</span>
        </label>
        <label class="check">
          <input type="checkbox" data-field="area-wellbeing"${areas.wellbeing ? " checked" : ""} />
          <span>Wohlbefinden</span>
        </label>
      </div>

      <div class="card">
        <div class="card-title">Wohlbefinden-Bilder</div>
        <div class="hint">
          Optionales eigenes Bild je Stufe. Dateiname unter <code>/config/www/</code>
          (z.\u00A0B. <code>stufe1.png</code> \u2192 <code>/local/stufe1.png</code>),
          <code>/local/...</code>-Pfad, HTTP(S)-URL oder PNG/JPEG/WebP-Data-URI.
          Leer = Emoji.
        </div>
        <div class="settings-grid">
          ${WELLBEING_STATES.map(
            (state) => `<label class="field">${escapeHtml(state.emoji)} ${escapeHtml(state.label)}
              <input type="text" data-field="wb-image-${escapeHtml(state.key)}"
                value="${attrValue(images[state.key] || "")}" autocomplete="off"
                placeholder="/local/${escapeHtml(state.key)}.png" />
            </label>`
          ).join("")}
        </div>
      </div>

      <div class="card">
        <div class="card-title">Quick-Drinks (max. ${SETTINGS_LIMITS.maxQuickDrinks})</div>
        <div class="muted">Ein leer gelassenes Label entfernt den Slot.</div>
        <div class="qd-list">${quickSlotsHtml(panel)}</div>
        <button class="btn ghost" type="button" data-action="qd-add"
          ${panel._quickDraft.length >= SETTINGS_LIMITS.maxQuickDrinks ? "disabled" : ""}>
          \uFF0B Slot hinzufügen
        </button>
      </div>

      <div class="card">
        <div class="card-title">Getränke-Lexikon</div>
        <div class="hint">
          Eine Zeile pro Eintrag: <code>wort=Typ,ml</code>
          (z.\u00A0B. <code>kaffee=Kaffee,250</code>). Zeilen mit <code>#</code> sind Kommentare.
        </div>
        <label class="field">Lexikon
          <textarea data-field="drink_lexicon" rows="10" spellcheck="false"
            autocapitalize="off" autocomplete="off">${escapeHtml(lexicon)}</textarea>
        </label>
      </div>

      <div class="card">
        <div class="card-title">Blutdruck-Warnschwellen</div>
        <div class="settings-grid">
          <label class="field">Systolisch
            <input type="number" inputmode="numeric" data-field="sys_threshold"
              min="${SETTINGS_LIMITS.thresholdMin}" max="${SETTINGS_LIMITS.thresholdMax}"
              value="${attrValue(sys)}" />
          </label>
          <label class="field">Diastolisch
            <input type="number" inputmode="numeric" data-field="dia_threshold"
              min="${SETTINGS_LIMITS.thresholdMin}" max="${SETTINGS_LIMITS.thresholdMax}"
              value="${attrValue(dia)}" />
          </label>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Datenhaltung</div>
        <div class="settings-grid">
          <label class="field">Retention (Monate, 0 = aus)
            <input type="number" inputmode="numeric" data-field="retention_months"
              min="${SETTINGS_LIMITS.retentionMin}" max="${SETTINGS_LIMITS.retentionMax}"
              value="${attrValue(retention)}" />
          </label>
        </div>
        <label class="check">
          <input type="checkbox" data-field="enable_sidebar_panel"${sidebar ? " checked" : ""} />
          <span>Sidebar-Panel anzeigen</span>
        </label>
      </div>

      <div class="card">
        <div class="card-title">Export</div>
        <div class="muted">Schreibt CSV-Dateien nach <code>/config/health_o_mat_export/</code>.</div>
        <div class="export-row">
          <label class="field">Datensatz
            <select data-field="export_dataset">
              ${EXPORT_DATASETS.map(
                (d) => `<option value="${escapeHtml(d.value)}">${escapeHtml(d.label)}</option>`
              ).join("")}
            </select>
          </label>
          <button class="btn" type="button" data-action="export"
            ${panel._exportBusy ? "disabled" : ""}>\u2B07 CSV-Export</button>
        </div>
        <div data-export-result>${exportResultHtml(panel)}</div>
      </div>

      <div data-settings-status>${settingsStatusHtml(panel)}</div>

      <div class="settings-actions">
        <button class="btn" type="submit" data-save-button
          ${panel._settingsBusy ? "disabled" : ""}>\u{1F4BE} Speichern</button>
        <button class="btn ghost" type="button" data-action="settings-reload"
          ${panel._settingsBusy ? "disabled" : ""}>\u21BB Neu laden</button>
      </div>
    </form>`;
}

function quickSlotsHtml(panel) {
  const fallbackIcon = SETTINGS_FALLBACKS.quick_icon;
  return panel._quickDraft
    .map(
      (slot, i) => `<div class="qd-slot" data-slot="${i}" data-key="${escapeHtml(slot.key || "")}">
        <label class="field">Label
          <input type="text" data-field="qd-label" data-index="${i}" autocomplete="off"
            value="${attrValue(slot.label)}" placeholder="z.\u00A0B. Glas Wasser" />
        </label>
        <label class="field">ml
          <input type="number" inputmode="numeric" data-field="qd-ml" data-index="${i}"
            min="${SETTINGS_LIMITS.quickMlMin}" max="${SETTINGS_LIMITS.quickMlMax}"
            value="${attrValue(slot.ml)}" />
        </label>
        <label class="field">Icon
          <input type="text" data-field="qd-icon" data-index="${i}" autocomplete="off"
            value="${attrValue(slot.icon || fallbackIcon)}" placeholder="mdi:cup-water" />
        </label>
        <button class="btn ghost" type="button" data-action="qd-remove" data-index="${i}"
          aria-label="Slot entfernen">\u2715</button>
      </div>`
    )
    .join("");
}

export function settingsStatusHtml(panel) {
  const status = panel._settingsStatus;
  if (!status) return "";
  return `<div class="settings-status ${status.ok ? "ok" : "err"}" role="status">${escapeHtml(status.text)}</div>`;
}

export function exportResultHtml(panel) {
  const result = panel._exportResult;
  if (!result) return "";
  return `<div class="settings-status ${result.ok ? "ok" : "err"}" role="status">${escapeHtml(result.text)}</div>`;
}

/* The export WS result shape is backend-defined; render defensively. */
export function exportResultText(res) {
  if (res == null) return "Export abgeschlossen.";
  if (typeof res === "string") return res;
  if (typeof res !== "object") return String(res);
  if (Array.isArray(res.files) && res.files.length) {
    return `Exportiert: ${res.files.map((f) => String(f)).join(", ")}`;
  }
  if (res.files && typeof res.files === "object") {
    const names = Object.keys(res.files).map((k) => String(res.files[k]));
    if (names.length) return `Exportiert: ${names.join(", ")}`;
  }
  if (res.filename) return `Exportiert: ${String(res.filename)}`;
  if (res.path) return `Exportiert: ${String(res.path)}`;
  if (res.message) return String(res.message);
  if (res.ok === true) {
    // Backend contract: { ok: true, entry_id, person, dataset }.
    const parts = [];
    if (res.person) parts.push(String(res.person));
    if (res.dataset) parts.push(datasetLabel(res.dataset));
    const what = parts.length ? ` (${parts.join(" \u00B7 ")})` : "";
    return `Export ausgel\u00F6st${what} \u2192 /config/health_o_mat_export/`;
  }
  if (typeof res.count === "number") return `Export abgeschlossen (${res.count} Zeilen).`;
  try {
    return JSON.stringify(res);
  } catch (_e) {
    return "Export abgeschlossen.";
  }
}

/* ---- Person management (D7) ---------------------------------------------- */

export function personsPanel(panel) {
  const persons = panel._persons || [];
  const busy = panel._adminBusy ? "disabled" : "";
  const rows = persons
    .map((p) => {
      const slug = personSlug(p);
      const isTarget = panel._deleteTarget === p.entry_id;
      const confirmBlock = isTarget
        ? `<div class="person-manage" data-delete-panel="${escapeHtml(p.entry_id)}">
            <div class="hint">Backups k\u00F6nnen derzeit <strong>nicht</strong> wiederhergestellt werden. Zum endg\u00FCltigen L\u00F6schen den Schl\u00FCssel <code>${escapeHtml(slug)}</code> eingeben.</div>
            <label class="field">Zur Best\u00E4tigung \u201E${escapeHtml(slug)}\u201C eingeben
              <input type="text" data-field="delete-confirm" autocomplete="off"
                autocapitalize="off" spellcheck="false" />
            </label>
            <div class="settings-actions">
              <button class="btn" type="button" data-action="delete-confirm"
                data-entry="${escapeHtml(p.entry_id)}"${panel._deleteBusy ? " disabled" : ""}>Endg\u00FCltig l\u00F6schen</button>
              <button class="btn ghost" type="button" data-action="delete-cancel"
                data-entry="${escapeHtml(p.entry_id)}">Abbrechen</button>
            </div>
          </div>`
        : "";
      return `<div class="person-manage" data-person="${escapeHtml(p.entry_id)}">
          <div class="kv"><span class="k">${escapeHtml(p.display_name)}</span><span class="v"><code>${escapeHtml(slug)}</code></span></div>
          <div class="settings-actions">
            <button class="btn ghost" type="button" data-action="delete-begin"
              data-entry="${escapeHtml(p.entry_id)}"${busy}>\u{1F5D1} L\u00F6schen</button>
          </div>
          ${confirmBlock}
        </div>`;
    })
    .join("");

  const list = persons.length
    ? `<div class="person-list">${rows}</div>`
    : `<div class="muted">Keine Person eingerichtet.</div>`;

  return `<div class="card">
      <div class="card-title">Personen</div>
      <div class="muted">Verwaltung der eingerichteten Personen (stabiler Schl\u00FCssel in Klammern).</div>
      ${list}
      ${adminStatusHtml(panel)}
      <div class="settings-actions">
        <button class="btn" type="button" data-action="person-add"${busy}>\uFF0B Person hinzuf\u00FCgen</button>
        <button class="btn ghost" type="button" data-action="backup"${busy}>\u{1F4BE} Backup erstellen</button>
      </div>
    </div>`;
}

export function adminStatusHtml(panel) {
  const status = panel._adminStatus;
  if (!status) return "";
  return `<div class="settings-status ${status.ok ? "ok" : "err"}" role="status">${escapeHtml(status.text)}</div>`;
}

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
  RESTORE_DATASETS,
  RESTORE_MODES,
  RESTORE_CONFIRM_WORD,
  WELLBEING_STATES,
  escapeHtml,
  attrValue,
  datasetLabel,
  normalizeAreas,
  personSlug,
  messageHtml,
  t,
} from "./health-o-mat-panel-base.js?v=0.14.1";

/* ---- Settings view ------------------------------------------------------- */

export function renderSettings(panel) {
  const head = `<div class="person-head"><span class="dot"></span><span>${escapeHtml(
    t("ui_admin_settings", "Einstellungen")
  )}</span></div>`;
  const persons = panel._persons || [];
  const personsCard = personsPanel(panel);
  if (!persons.length) {
    return `${head}${personsCard}${messageHtml(
      t("ui_common_no_person", "Keine Person eingerichtet."),
      false
    )}`;
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
      : messageHtml(t("ui_admin_loading", "Lade Einstellungen…"), false);
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
  const auditLimit = s.audit_limit == null ? SETTINGS_FALLBACKS.audit_limit : s.audit_limit;
  const sidebar = s.enable_sidebar_panel === true;
  const lexicon = s.drink_lexicon == null ? "" : String(s.drink_lexicon);
  const display = s.person_display == null ? "" : String(s.person_display);
  const areas = normalizeAreas(s.areas);
  const images =
    s.wellbeing_images && typeof s.wellbeing_images === "object" ? s.wellbeing_images : {};
  const confirmWellbeing =
    s.wellbeing_confirm == null
      ? SETTINGS_FALLBACKS.wellbeing_confirm
      : s.wellbeing_confirm === true;

  const banner = loadError
    ? `<div class="banner" role="alert">\u26A0\uFE0F ${escapeHtml(loadError)}</div>`
    : "";

  return `<form class="settings-form" data-form="settings">
      ${banner}
      <div class="card">
        <div class="card-title">${escapeHtml(t("ui_admin_general", "Allgemein"))}</div>
        <div class="settings-grid">
          <label class="field">${escapeHtml(t("ui_admin_goal", "Tagesziel (ml)"))}
            <input type="number" inputmode="numeric" data-field="daily_goal_ml"
              min="${SETTINGS_LIMITS.goalMin}" max="${SETTINGS_LIMITS.goalMax}"
              value="${attrValue(goal)}" />
          </label>
          <label class="field">${escapeHtml(
            t("ui_admin_reset", "Tages-Reset (Stunde, 0–23)")
          )}
            <input type="number" inputmode="numeric" data-field="daily_reset_hour"
              min="${SETTINGS_LIMITS.resetMin}" max="${SETTINGS_LIMITS.resetMax}"
              value="${attrValue(reset)}" />
          </label>
          <label class="field">${escapeHtml(t("ui_admin_display_name", "Anzeigename"))}
            <input type="text" data-field="person_display" autocomplete="off"
              value="${attrValue(display)}" />
          </label>
        </div>
      </div>

      <div class="card">
        <div class="card-title">${escapeHtml(t("ui_admin_areas", "Bereiche"))}</div>
        <div class="muted">${escapeHtml(
          t(
            "ui_admin_areas_hint",
            "Abgewählte Bereiche werden in Übersicht und Detail ausgeblendet."
          )
        )}</div>
        <label class="check">
          <input type="checkbox" data-field="area-drink"${areas.drink ? " checked" : ""} />
          <span>${escapeHtml(t("ui_common_area_drink", "Trinken"))}</span>
        </label>
        <label class="check">
          <input type="checkbox" data-field="area-bp"${areas.bp ? " checked" : ""} />
          <span>${escapeHtml(t("ui_common_area_bp", "Blutdruck"))}</span>
        </label>
        <label class="check">
          <input type="checkbox" data-field="area-wellbeing"${areas.wellbeing ? " checked" : ""} />
          <span>${escapeHtml(t("ui_common_area_wellbeing", "Wohlbefinden"))}</span>
        </label>
      </div>

      <div class="card">
        <div class="card-title">${escapeHtml(
          t("ui_admin_wb_images", "Wohlbefinden-Bilder")
        )}</div>
        <div class="hint">${escapeHtml(
          t(
            "ui_admin_wb_images_hint",
            "Optionales eigenes Bild je Stufe. Dateiname unter /config/www/ " +
              "(z. B. stufe1.png → /local/stufe1.png), /local/...-Pfad, HTTP(S)-URL " +
              "oder PNG/JPEG/WebP-Data-URI. Leer = Emoji."
          )
        )}</div>
        <label class="check">
          <input type="checkbox" data-field="wellbeing_confirm"${confirmWellbeing ? " checked" : ""} />
          <span>${escapeHtml(
            t("ui_admin_wb_confirm", "Wohlbefinden: Bestätigung vor Übernahme")
          )}</span>
        </label>
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
        <div class="card-title">${escapeHtml(
          t("ui_admin_quick_drinks", "Quick-Drinks (max. {max})", {
            max: SETTINGS_LIMITS.maxQuickDrinks,
          })
        )}</div>
        <div class="muted">${escapeHtml(
          t("ui_admin_quick_hint", "Ein leer gelassenes Label entfernt den Slot.")
        )}</div>
        <div class="qd-list">${quickSlotsHtml(panel)}</div>
        <button class="btn ghost" type="button" data-action="qd-add"
          ${panel._quickDraft.length >= SETTINGS_LIMITS.maxQuickDrinks ? "disabled" : ""}>
          \uFF0B ${escapeHtml(t("ui_admin_quick_add", "+ Slot hinzufügen"))}
        </button>
      </div>

      <div class="card">
        <div class="card-title">${escapeHtml(
          t("ui_admin_lexicon_title", "Getränke-Lexikon")
        )}</div>
        <div class="hint">
          ${escapeHtml(
            t(
              "ui_admin_lexicon_hint",
              "Eine Zeile pro Eintrag: wort=Typ,ml (z. B. kaffee=Kaffee,250). " +
                "Zeilen mit # sind Kommentare."
            )
          )}
        </div>
        <label class="field">${escapeHtml(t("ui_admin_lexicon_field", "Lexikon"))}
          <textarea data-field="drink_lexicon" rows="10" spellcheck="false"
            autocapitalize="off" autocomplete="off">${escapeHtml(lexicon)}</textarea>
        </label>
      </div>

      <div class="card">
        <div class="card-title">${escapeHtml(
          t("ui_admin_bp_thresholds", "Blutdruck-Warnschwellen")
        )}</div>
        <div class="settings-grid">
          <label class="field">${escapeHtml(t("ui_panel_chart_bp_systolic", "Systolisch"))}
            <input type="number" inputmode="numeric" data-field="sys_threshold"
              min="${SETTINGS_LIMITS.thresholdMin}" max="${SETTINGS_LIMITS.thresholdMax}"
              value="${attrValue(sys)}" />
          </label>
          <label class="field">${escapeHtml(t("ui_panel_chart_bp_diastolic", "Diastolisch"))}
            <input type="number" inputmode="numeric" data-field="dia_threshold"
              min="${SETTINGS_LIMITS.thresholdMin}" max="${SETTINGS_LIMITS.thresholdMax}"
              value="${attrValue(dia)}" />
          </label>
        </div>
      </div>

      <div class="card">
        <div class="card-title">${escapeHtml(t("ui_admin_storage", "Datenhaltung"))}</div>
        <div class="settings-grid">
          <label class="field">${escapeHtml(
            t("ui_admin_retention", "Retention (Monate, 0 = aus)")
          )}
            <input type="number" inputmode="numeric" data-field="retention_months"
              min="${SETTINGS_LIMITS.retentionMin}" max="${SETTINGS_LIMITS.retentionMax}"
              value="${attrValue(retention)}" />
          </label>
          <label class="field">${escapeHtml(
            t("ui_admin_audit", "Audit-Log-Limit (0 = unbegrenzt)")
          )}
            <input type="number" inputmode="numeric" data-field="audit_limit"
              min="${SETTINGS_LIMITS.auditMin}" max="${SETTINGS_LIMITS.auditMax}"
              value="${attrValue(auditLimit)}" />
          </label>
        </div>
        <label class="check">
          <input type="checkbox" data-field="enable_sidebar_panel"${sidebar ? " checked" : ""} />
          <span>${escapeHtml(t("ui_admin_sidebar", "Sidebar-Panel anzeigen"))}</span>
        </label>
      </div>

      <div class="card">
        <div class="card-title">${escapeHtml(t("ui_admin_export", "Export"))}</div>
        <div class="muted">${escapeHtml(
          t("ui_admin_export_hint", "Schreibt CSV-Dateien nach /config/health_o_mat_export/.")
        )}</div>
        <div class="export-row">
          <label class="field">${escapeHtml(t("ui_admin_dataset", "Datensatz"))}
            <select data-field="export_dataset">
              ${EXPORT_DATASETS.map(
                (d) => `<option value="${escapeHtml(d.value)}">${escapeHtml(
                  t(d.labelKey, d.label)
                )}</option>`
              ).join("")}
            </select>
          </label>
          <button class="btn" type="button" data-action="export"
            ${panel._exportBusy ? "disabled" : ""}>\u2B07 ${escapeHtml(t("ui_admin_export_btn", "CSV-Export"))}</button>
        </div>
        <div data-export-result>${exportResultHtml(panel)}</div>
      </div>

      ${restoreCard(panel)}

      <div data-settings-status>${settingsStatusHtml(panel)}</div>

      <div class="settings-actions">
        <button class="btn" type="submit" data-save-button
          ${panel._settingsBusy ? "disabled" : ""}>\u{1F4BE} ${escapeHtml(t("ui_common_save", "Speichern"))}</button>
        <button class="btn ghost" type="button" data-action="settings-reload"
          ${panel._settingsBusy ? "disabled" : ""}>\u21BB ${escapeHtml(t("ui_admin_reload", "Neu laden"))}</button>
      </div>
    </form>`;
}

function quickSlotsHtml(panel) {
  const fallbackIcon = SETTINGS_FALLBACKS.quick_icon;
  return panel._quickDraft
    .map(
      (slot, i) => `<div class="qd-slot" data-slot="${i}" data-key="${escapeHtml(slot.key || "")}">
        <label class="field">${escapeHtml(t("ui_admin_label", "Label"))}
          <input type="text" data-field="qd-label" data-index="${i}" autocomplete="off"
            value="${attrValue(slot.label)}" placeholder="${escapeHtml(
              t("ui_admin_quick_placeholder", "z. B. Glas Wasser")
            )}" />
        </label>
        <label class="field">ml
          <input type="number" inputmode="numeric" data-field="qd-ml" data-index="${i}"
            min="${SETTINGS_LIMITS.quickMlMin}" max="${SETTINGS_LIMITS.quickMlMax}"
            value="${attrValue(slot.ml)}" />
        </label>
        <label class="field">${escapeHtml(t("ui_admin_icon", "Icon"))}
          <input type="text" data-field="qd-icon" data-index="${i}" autocomplete="off"
            value="${attrValue(slot.icon || fallbackIcon)}" placeholder="mdi:cup-water" />
        </label>
        <button class="btn ghost" type="button" data-action="qd-remove" data-index="${i}"
          aria-label="${escapeHtml(
            t("ui_admin_slot_remove", "Slot entfernen")
          )}">\u2715</button>
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
  if (res == null) return t("ui_admin_export_done", "Export abgeschlossen.");
  if (typeof res === "string") return res;
  if (typeof res !== "object") return String(res);
  if (Array.isArray(res.files) && res.files.length) {
    return t("ui_admin_exported", "Exportiert: {files}", {
      files: res.files.map((f) => String(f)).join(", "),
    });
  }
  if (res.files && typeof res.files === "object") {
    const names = Object.keys(res.files).map((k) => String(res.files[k]));
    if (names.length) {
      return t("ui_admin_exported", "Exportiert: {files}", { files: names.join(", ") });
    }
  }
  if (res.filename) {
    return t("ui_admin_exported", "Exportiert: {files}", { files: String(res.filename) });
  }
  if (res.path) {
    return t("ui_admin_exported", "Exportiert: {files}", { files: String(res.path) });
  }
  if (res.message) return String(res.message);
  if (res.ok === true) {
    // Backend contract: { ok: true, entry_id, person, dataset }.
    const parts = [];
    if (res.person) parts.push(String(res.person));
    if (res.dataset) parts.push(datasetLabel(res.dataset));
    const what = parts.length ? ` (${parts.join(" \u00B7 ")})` : "";
    return t(
      "ui_admin_export_triggered",
      "Export ausgelöst{what} → /config/health_o_mat_export/",
      { what }
    );
  }
  if (typeof res.count === "number") {
    return t("ui_admin_export_rows", "Export abgeschlossen ({count} Zeilen).", {
      count: res.count,
    });
  }
  try {
    return JSON.stringify(res);
  } catch (_e) {
    return t("ui_admin_export_done", "Export abgeschlossen.");
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
            <div class="hint">${escapeHtml(
              t(
                "ui_admin_delete_warning",
                "Backups können derzeit nicht wiederhergestellt werden. Zum endgültigen Löschen den Schlüssel {slug} eingeben.",
                { slug }
              )
            )}</div>
            <label class="field">${escapeHtml(
              t("ui_admin_delete_confirm_label", "Zur Bestätigung „{slug}“ eingeben", { slug })
            )}
              <input type="text" data-field="delete-confirm" autocomplete="off"
                autocapitalize="off" spellcheck="false" />
            </label>
            <div class="settings-actions">
              <button class="btn" type="button" data-action="delete-confirm"
                data-entry="${escapeHtml(p.entry_id)}"${panel._deleteBusy ? " disabled" : ""}>${escapeHtml(
                t("ui_admin_delete_forever", "Endgültig löschen")
              )}</button>
              <button class="btn ghost" type="button" data-action="delete-cancel"
                data-entry="${escapeHtml(p.entry_id)}">${escapeHtml(
                  t("ui_common_cancel", "Abbrechen")
                )}</button>
            </div>
          </div>`
        : "";
      return `<div class="person-manage" data-person="${escapeHtml(p.entry_id)}">
          <div class="kv"><span class="k">${escapeHtml(p.display_name)}</span><span class="v"><code>${escapeHtml(slug)}</code></span></div>
          <div class="settings-actions">
            <button class="btn ghost" type="button" data-action="delete-begin"
              data-entry="${escapeHtml(p.entry_id)}"${busy}>\u{1F5D1} ${escapeHtml(t("ui_common_delete", "Löschen"))}</button>
          </div>
          ${confirmBlock}
        </div>`;
    })
    .join("");

  const list = persons.length
    ? `<div class="person-list">${rows}</div>`
    : `<div class="muted">${escapeHtml(
        t("ui_common_no_person", "Keine Person eingerichtet.")
      )}</div>`;

  return `<div class="card">
      <div class="card-title">${escapeHtml(t("ui_admin_persons", "Personen"))}</div>
      <div class="muted">${escapeHtml(
        t(
          "ui_admin_persons_hint",
          "Verwaltung der eingerichteten Personen (stabiler Schlüssel in Klammern)."
        )
      )}</div>
      ${list}
      ${adminStatusHtml(panel)}
      <div class="settings-actions">
        <button class="btn" type="button" data-action="person-add"${busy}>\uFF0B ${escapeHtml(
          t("ui_admin_person_add", "+ Person hinzufügen")
        )}</button>
        <button class="btn ghost" type="button" data-action="backup"${busy}>\u{1F4BE} ${escapeHtml(
          t("ui_admin_backup_create", "Backup erstellen")
        )}</button>
      </div>
    </div>`;
}

export function adminStatusHtml(panel) {
  const status = panel._adminStatus;
  if (!status) return "";
  return `<div class="settings-status ${status.ok ? "ok" : "err"}" role="status">${escapeHtml(status.text)}</div>`;
}

/* ---- Restore-Verwaltung (REQ-HOM-116 UI) --------------------------------- */

function restoreFieldValue(value) {
  return value == null ? "" : String(value);
}

function restoreFileOptions(panel) {
  const files = Array.isArray(panel._restoreFiles) ? panel._restoreFiles : [];
  const current = String((panel._restoreDraft && panel._restoreDraft.filename) || "");
  if (!files.length) {
    return `<option value="">${escapeHtml(
      t("ui_admin_no_backup_file", "— keine Backup-Datei vorhanden —")
    )}</option>`;
  }
  return files
    .map(
      (name) =>
        `<option value="${escapeHtml(name)}"${name === current ? " selected" : ""}>${escapeHtml(
          name
        )}</option>`
    )
    .join("");
}

/* Payload aus dem Draft bauen — dieselben Felder wie `restore_backup`
 * (keine zweite Semantik). Gibt `{ ok, payload }` oder `{ ok: false, error }`.
 * `options.dryRun` erlaubt einen Replace-Dry-Run ohne REPLACE-Bestätigung
 * (N-7); nur der echte Apply-Lauf verlangt sie. */
export function collectRestorePayload(panel, options) {
  const dryRun = !!(options && options.dryRun);
  const draft = panel._restoreDraft || {};
  const filename = String(draft.filename == null ? "" : draft.filename).trim();
  if (!filename) {
    return { ok: false, error: t("ui_admin_err_no_file", "Bitte eine Backup-Datei auswählen.") };
  }
  const mode = draft.mode === "replace" ? "replace" : "merge";

  const allowed = RESTORE_DATASETS.map((dataset) => dataset.value);
  const selected = allowed.filter((value) => {
    const flags = draft.datasets || {};
    return flags[value] !== false;
  });
  if (!selected.length) {
    return {
      ok: false,
      error: t("ui_admin_err_no_dataset", "Bitte mindestens einen Datensatz auswählen."),
    };
  }

  const from = String(draft.from == null ? "" : draft.from).trim();
  const to = String(draft.to == null ? "" : draft.to).trim();
  for (const [label, value] of [
    [t("ui_admin_from", "Von (optional)"), from],
    [t("ui_admin_to", "Bis (optional)"), to],
  ]) {
    if (value && !Number.isFinite(Date.parse(value))) {
      return {
        ok: false,
        error: t(
          "ui_admin_err_invalid_time",
          "Zeitraum: „{label}“ ist kein gültiger Zeitpunkt.",
          { label }
        ),
      };
    }
  }
  if (from && to && Date.parse(to) < Date.parse(from)) {
    return { ok: false, error: t("ui_admin_err_range", "Zeitraum: „Bis“ liegt vor „Von“.") };
  }

  const personMapRaw = String(draft.personMap == null ? "" : draft.personMap).trim();
  let personMap = null;
  if (personMapRaw) {
    try {
      personMap = JSON.parse(personMapRaw);
    } catch (_e) {
      return {
        ok: false,
        error: t("ui_admin_err_map_json", "Personen-Mapping: kein gültiges JSON."),
      };
    }
    if (!personMap || typeof personMap !== "object" || Array.isArray(personMap)) {
      return {
        ok: false,
        error: t(
          "ui_admin_err_map_shape",
          "Personen-Mapping: JSON-Objekt {Quelle: Ziel-Entry-ID} erwartet."
        ),
      };
    }
  }

  const confirm = String(draft.confirm == null ? "" : draft.confirm).trim();
  if (mode === "replace" && !dryRun && confirm !== RESTORE_CONFIRM_WORD) {
    return {
      ok: false,
      error: t(
        "ui_admin_err_confirm",
        "Zum Ersetzen muss die Bestätigung „{word}“ eingegeben werden.",
        { word: RESTORE_CONFIRM_WORD }
      ),
    };
  }

  const payload = { filename, mode };
  // Alle Datensätze = Default des Backends; nur eine Teilmenge wird gesendet.
  if (selected.length < allowed.length) payload.datasets = selected;
  // S-1: `datetime-local` ist lokale Browserzeit ohne Zone — als UTC-ISO
  // senden, damit der Server den Zeitraum eindeutig interpretiert.
  if (from) payload.from = new Date(from).toISOString();
  if (to) payload.to = new Date(to).toISOString();
  if (personMap) payload.person_map = personMap;
  if (mode === "replace" && confirm === RESTORE_CONFIRM_WORD) {
    payload.confirm = RESTORE_CONFIRM_WORD;
  }
  return { ok: true, payload };
}

export function restoreCard(panel) {
  const draft = panel._restoreDraft || {};
  const files = Array.isArray(panel._restoreFiles) ? panel._restoreFiles : [];
  const busy = !!(panel._restoreBusy || panel._restoreFilesBusy);
  const disabled = busy ? " disabled" : "";
  const datasets = draft.datasets || {};
  const mode = draft.mode === "replace" ? "replace" : "merge";
  const advanced = !!draft.advanced || !!(draft.personMap || draft.from || draft.to);

  const datasetChecks = RESTORE_DATASETS.map(
    (dataset) => `<label class="check">
        <input type="checkbox" data-field="restore-dataset-${escapeHtml(dataset.value)}"${
          datasets[dataset.value] !== false ? " checked" : ""
        }${disabled} />
        <span>${escapeHtml(t(dataset.labelKey, dataset.label))}</span>
      </label>`
  ).join("");

  const modeOptions = RESTORE_MODES.map(
    (item) =>
      `<option value="${escapeHtml(item.value)}"${item.value === mode ? " selected" : ""}>${escapeHtml(
        t(item.labelKey, item.label)
      )}</option>`
  ).join("");

  const filesError = panel._restoreFilesError
    ? `<div class="banner" role="alert">\u26A0\uFE0F ${escapeHtml(panel._restoreFilesError)}</div>`
    : "";
  const error = panel._restoreError
    ? `<div class="banner" role="alert">\u26A0\uFE0F ${escapeHtml(panel._restoreError)}</div>`
    : "";
  const busyText = panel._restoreFilesBusy
    ? t("ui_admin_loading_files", "Lade Dateiliste…")
    : panel._restoreBusy
      ? t("ui_admin_restore_running", "Restore läuft…")
      : "";
  const busyHtml = busyText
    ? `<div class="settings-status ok" role="status">${escapeHtml(busyText)}</div>`
    : "";

  const confirmRow =
    mode === "replace"
      ? `<label class="field">${escapeHtml(
          t("ui_admin_confirm_label", "Bestätigung ({word} eingeben)", {
            word: RESTORE_CONFIRM_WORD,
          })
        )}
          <input type="text" data-field="restore-confirm" autocomplete="off"
            autocapitalize="characters" spellcheck="false"
            value="${attrValue(draft.confirm || "")}"${disabled} />
        </label>`
      : "";

  const fileHint = files.length
    ? `<div class="hint">${escapeHtml(
        files.length === 1
          ? t("ui_admin_files_count_one", "{count} Datei in den Backup-Ordnern.", {
              count: files.length,
            })
          : t(
              "ui_admin_files_count_other",
              "{count} Dateien in den Backup-Ordnern.",
              { count: files.length }
            )
      )}</div>`
    : `<div class="hint">${escapeHtml(
        t(
          "ui_admin_files_hint",
          "Backups und Sicherheitsbackups aus /config/health_o_mat_import/ und /config/health_o_mat_export/ erscheinen hier."
        )
      )}</div>`;

  return `<div class="card" data-restore-card>
      <div class="card-title">${escapeHtml(
        t("ui_admin_restore_title", "Wiederherstellen")
      )}</div>
      <div class="hint">${escapeHtml(
        t(
          "ui_admin_restore_hint",
          "Spielt ein JSON-Backup kontrolliert ein. Ein Dry-Run zeigt die Auswirkungen, ohne zu schreiben."
        )
      )}</div>
      <div class="restore-row">
        <label class="field">${escapeHtml(
          t("ui_admin_restore_file", "Backup-Datei")
        )}
          <select data-field="restore-filename"${disabled}>${restoreFileOptions(panel)}</select>
        </label>
        <button class="btn ghost" type="button" data-action="restore-files-refresh"${
          panel._restoreFilesBusy ? " disabled" : ""
        }>\u21BB ${escapeHtml(
          t("ui_admin_refresh_files", "Dateien aktualisieren")
        )}</button>
      </div>
      ${fileHint}
      ${filesError}
      <label class="field">${escapeHtml(t("ui_admin_mode", "Modus"))}
        <select data-field="restore-mode"${disabled}>${modeOptions}</select>
      </label>
      <div class="restore-datasets">${datasetChecks}</div>
      <div class="settings-grid">
        <label class="field">${escapeHtml(t("ui_admin_from", "Von (optional)"))}
          <input type="datetime-local" data-field="restore-from"
            value="${attrValue(restoreFieldValue(draft.from))}"${disabled} />
        </label>
        <label class="field">${escapeHtml(t("ui_admin_to", "Bis (optional)"))}
          <input type="datetime-local" data-field="restore-to"
            value="${attrValue(restoreFieldValue(draft.to))}"${disabled} />
        </label>
      </div>
      <details class="restore-advanced" data-restore-advanced${advanced ? " open" : ""}>
        <summary>${escapeHtml(
          t("ui_admin_advanced", "Erweitert: Personen-Mapping")
        )}</summary>
        <div class="hint">${escapeHtml(
          t(
            "ui_admin_person_map_hint",
            'JSON-Objekt {Quelle: Ziel-Entry-ID}, z. B. {"anna": "abc123"}. Leer = automatische Zuordnung.'
          )
        )}</div>
        <label class="field">${escapeHtml(
          t("ui_admin_person_map", "Personen-Mapping (JSON)")
        )}
          <textarea data-field="restore-person-map" spellcheck="false"
            autocomplete="off" placeholder='{"quelle": "ziel-entry-id"}'${disabled}>${escapeHtml(
              restoreFieldValue(draft.personMap)
            )}</textarea>
        </label>
      </details>
      ${confirmRow}
      ${busyHtml}
      ${error}
      <div class="settings-actions">
        <button class="btn ghost" type="button" data-action="restore-dry-run"${
          busy || !files.length ? " disabled" : ""
        }>${escapeHtml(t("ui_admin_dry_run", "Dry-Run"))}</button>
        <button class="btn" type="button" data-action="restore-apply"${
          busy || !files.length ? " disabled" : ""
        }>${escapeHtml(
          t("ui_admin_restore_title", "Wiederherstellen")
        )}</button>
      </div>
      ${restoreResultHtml(panel)}
    </div>`;
}

function restorePersonLabel(panel, entryId) {
  const id = String(entryId == null ? "" : entryId);
  const hit = (panel._persons || []).find((person) => person.entry_id === id);
  return hit ? hit.display_name : id;
}

function restoreTotals(panel) {
  const result = panel._restoreResult;
  if (!result || !result.data) return null;
  const data = result.data;
  const plan = data.plan && typeof data.plan === "object" ? data.plan : {};
  const source = plan.totals || data.totals || null;
  if (source && typeof source === "object") {
    return {
      added: Number(source.added) || 0,
      skipped: Number(source.skipped) || 0,
      conflicts: Number(source.conflicts) || 0,
      errors: Number(source.errors) || 0,
    };
  }
  return { added: 0, skipped: 0, conflicts: 0, errors: 0 };
}

export function restoreResultHtml(panel) {
  const result = panel._restoreResult;
  if (!result || !result.data) return "";
  const data = result.data;
  const plan = data.plan && typeof data.plan === "object" ? data.plan : {};
  const totals = restoreTotals(panel);
  if (!totals) return "";
  const counts = t(
    "ui_admin_counts",
    "{added} hinzugefügt, {skipped} übersprungen, {conflicts} Konflikte, {errors} Fehler",
    totals
  );
  const changes = plan.has_changes === true || data.applied === true;
  const mode = String(data.mode || plan.mode || "merge");
  const replace = mode === "replace";
  const headline = result.dryRun
    ? t(
        replace ? "ui_admin_dry_run_replace" : "ui_admin_dry_run_merge",
        replace ? "Dry-Run (Ersetzen): {counts}." : "Dry-Run (Zusammenführen): {counts}.",
        { counts }
      )
    : t(
        replace ? "ui_admin_restored_replace" : "ui_admin_restored_merge",
        replace
          ? "Wiederhergestellt (Ersetzen): {counts}."
          : "Wiederhergestellt (Zusammenführen): {counts}.",
        { counts }
      );
  const changeText = result.dryRun
    ? changes
      ? t("ui_admin_changes_would_apply", "Änderungen würden übernommen.")
      : t(
          "ui_admin_no_changes_would_write",
          "Keine Änderungen — es würde nichts geschrieben."
        )
    : changes
      ? t("ui_admin_changes_applied", "Änderungen wurden übernommen.")
      : t("ui_admin_no_changes_applied", "Keine Änderungen übernommen.");

  const persons = plan.persons && typeof plan.persons === "object" ? plan.persons : {};
  const personRows = Object.keys(persons)
    .map(
      (source) =>
        `<li><code>${escapeHtml(source)}</code> \u2192 ${escapeHtml(
          restorePersonLabel(panel, persons[source])
        )}</li>`
    )
    .join("");
  const personsHtml = personRows
    ? `<div class="muted">${escapeHtml(t("ui_admin_persons", "Personen"))}</div><ul>${personRows}</ul>`
    : "";

  const warnings = Array.isArray(plan.warnings) ? plan.warnings : data.warnings;
  const warningRows = (Array.isArray(warnings) ? warnings : [])
    .map((warning) => `<li>${escapeHtml(warning)}</li>`)
    .join("");
  const warningsHtml = warningRows
    ? `<div class="muted">${escapeHtml(t("ui_admin_warnings", "Warnungen"))}</div><ul>${warningRows}</ul>`
    : "";

  const actions = Array.isArray(plan.actions) ? plan.actions.slice(0, 10) : [];
  const actionRows = actions
    .map((action) => {
      const target = restorePersonLabel(panel, action && action.target);
      const dataset = action && action.dataset ? String(action.dataset) : "?";
      const op = action && action.op ? String(action.op) : "?";
      const extra =
        action && action.op === "replace"
          ? ` ${t(
              "ui_admin_replaced_added",
              "({removed} ersetzt, {added} neu)",
              {
                removed: Number(action.removed) || 0,
                added: Number(action.added) || 0,
              }
            )}`
          : "";
      return `<li>${escapeHtml(`${dataset}: ${op} \u00B7 ${target}${extra}`)}</li>`;
    })
    .join("");
  const truncated = plan.actions_truncated
    ? `<li class="muted">${escapeHtml(
        t("ui_admin_more_actions", "… weitere Aktionen ausgeblendet.")
      )}</li>`
    : "";
  const actionsHtml = actionRows
    ? `<div class="muted">${escapeHtml(
        plan.actions_truncated
          ? t("ui_admin_actions_truncated", "Aktionen (gekürzt)")
          : t("ui_admin_actions", "Aktionen")
      )}</div><ul>${actionRows}${truncated}</ul>`
    : "";

  const backup = data.backup_path
    ? `<div class="muted">${escapeHtml(
        t("ui_admin_backup_path", "Sicherheitsbackup: {path}", {
          path: data.backup_path,
        })
      )}</div>`
    : "";

  return `<div class="restore-result ok" role="status" data-restore-result>
      <strong>${escapeHtml(headline)}</strong>
      <div>${escapeHtml(changeText)}</div>
      ${backup}
      ${personsHtml}
      ${warningsHtml}
      ${actionsHtml}
    </div>`;
}

/**
 * Health-O-Mat — Panel views module.
 *
 * Overview grid + person detail (tabs Trinken | Blutdruck | Wohlbefinden).
 * Pure rendering: every function receives the live panel element and only reads
 * its state / live-state helpers — it never mutates persistence or the DOM
 * directly. Area toggles hide disabled sections and tabs.
 *
 * Import specifier carries the integration version (cache-buster, see base).
 */

import {
  QUICK_DRINKS,
  WELLBEING_STATES,
  WELLBEING_SCORE_MAX,
  PACE_INFO,
  HISTORY_LIMIT,
  HISTORY_KIND_LABELS,
  HISTORY_KIND_KEYS,
  escapeHtml,
  attrValue,
  toNumber,
  clamp,
  fmtMl,
  localDateTimeValue,
  entryTime,
  ringHtml,
  categoryInfo,
  messageHtml,
  enabledTabs,
  areasForPerson,
  wellbeingScore,
  wellbeingChartHtml,
  wellbeingScale,
  wellbeingVisual,
  bpHistoryChartHtml,
  labBadge,
  labReportedSubline,
  labChartHtml,
  labMarkerOptionsHtml,
  labDisplayName,
  t,
  WS,
  errMsg,
} from "./health-o-mat-panel-base.js?v=0.16.2";

/* ---- Overview (L2 start) ------------------------------------------------- */

export function renderOverview(panel) {
  const tiles = (panel._persons || []).map((person) => renderTile(panel, person)).join("");
  return `<div class="grid">${tiles}</div>`;
}

export function renderTile(panel, person) {
  const entryId = person.entry_id;
  const data = panel._data[entryId];
  const error = panel._entryErrors[entryId];
  const areas = areasForPerson(person, data);

  if (!data) {
    const note = error
      ? `<div class="tile-row muted">${escapeHtml(error)}</div>`
      : `<div class="tile-row muted">${escapeHtml(t("ui_common_loading", "Lade\u2026"))}</div>`;
    return `<div class="tile loading">
        <div class="tile-head"><span class="dot"></span><span class="tile-name">${escapeHtml(person.display_name)}</span></div>
        ${note}
      </div>`;
  }

  const goal = toNumber(data.goal_ml, 0);
  const fallbackMl = toNumber(data.today && data.today.ml, 0);
  const ml = panel._liveNumber(data, "drinks_today", fallbackMl);
  const fallbackPct = goal > 0 ? (ml / goal) * 100 : 0;
  const percent = panel._liveNumber(
    data,
    "percent",
    toNumber(data.today && data.today.percent, fallbackPct)
  );
  const warn = areas.bp ? panel._isWarning(data) : false;

  const bp = data.bp || {};
  const sys = panel._liveNumber(data, "bp_sys", toNumber(bp.sys, NaN));
  const dia = panel._liveNumber(data, "bp_dia", toNumber(bp.dia, NaN));
  const pulse = panel._liveNumber(data, "bp_pulse", toNumber(bp.pulse, NaN));
  const bpText = Number.isFinite(sys) && Number.isFinite(dia)
    ? `${Math.round(sys)}/${Math.round(dia)}${Number.isFinite(pulse) ? ` \u00B7 ${Math.round(pulse)}` : ""}`
    : t("ui_panel_no_measurement", "keine Messung");

  const wb = data.wellbeing || {};
  const wbState = wellbeingView(panel, data);
  const wbAt = wb.at ? entryTime(wb.at) : "";

  /* Laborwerte (REQ-HOM-122): Zaehler + Kachelzeile rein aus dem bereits
   * geladenen `panel_data`-Block — kein zusaetzlicher Request (§7.3). */
  const labCount = areas.labs ? _labWarningCount(data) : 0;
  const labWarn = labCount > 0;
  const labRow = areas.labs
    ? `<div class="tile-row lab-row-tile"><span class="em" aria-hidden="true">\u{1F9EA}</span><span>${
        labWarn
          ? escapeHtml(
              t("ui_panel_tile_lab_warning", "{count} Marker außerhalb Referenz", {
                count: labCount,
              })
            )
          : escapeHtml(t("ui_panel_tile_lab_ok", "Alles im Bereich"))
      }</span>${labWarn ? `<span class="muted">\u00B7 \u26A0\uFE0F</span>` : ""}</div>`
    : "";

  /* Ein einziges ⚠-Badge, Tooltip nennt beide Ursachen, wenn beide zutreffen. */
  const warnTitleParts = [];
  if (warn) {
    warnTitleParts.push(t("ui_panel_bp_threshold_title", "Blutdruck oberhalb der Schwellen"));
  }
  if (labWarn) {
    warnTitleParts.push(
      t("ui_panel_lab_threshold_title", "{count} Laborwerte außerhalb Referenz", {
        count: labCount,
      })
    );
  }

  const rest = goal > 0 ? Math.max(0, Math.round(goal - ml)) : null;
  const sub = goal > 0
    ? `${t("ui_panel_tile_goal", "Ziel {ml}", { ml: fmtMl(goal) })}${
        rest ? ` \u00B7 ${t("ui_panel_tile_rest", "Rest {ml}", { ml: fmtMl(rest) })}` : ""
      }`
    : t("ui_panel_no_goal", "Kein Tagesziel gesetzt");

  const drinkSection = areas.drink
    ? `<div class="tile-main">
          ${ringHtml(percent, { compact: true })}
          <div class="tile-stats">
            <div class="tile-ml">${fmtMl(ml)}</div>
            <div class="tile-sub">${escapeHtml(sub)}</div>
          </div>
        </div>`
    : "";
  const bpRow = areas.bp
    ? `<div class="tile-row"><span class="em" aria-hidden="true">\u{1FA78}</span><span>${escapeHtml(bpText)}</span>${warn ? `<span class="muted">\u00B7 \u26A0\uFE0F</span>` : ""}</div>`
    : "";
  const wbRow = areas.wellbeing
    ? `<div class="tile-row">${wellbeingVisual(wbState)}<span>${escapeHtml(wbState.label)}</span>${wbAt ? `<span class="muted">\u00B7 ${escapeHtml(wbAt)}</span>` : ""}</div>`
    : "";

  return `<button class="tile" data-action="open" data-entry="${escapeHtml(entryId)}" type="button">
      <div class="tile-head">
        <span class="dot"></span>
        <span class="tile-name">${escapeHtml(person.display_name)}</span>
        ${
          warn || labWarn
            ? `<span class="status bad" title="${escapeHtml(
                warnTitleParts.join("; ")
              )}">\u26A0\uFE0F</span>`
            : ""
        }
      </div>
      ${drinkSection}
      ${bpRow}
      ${wbRow}
      ${labRow}
    </button>`;
}

/* ---- Detail -------------------------------------------------------------- */

export function renderDetail(panel) {
  const entryId = panel._selectedEntry;
  const person = (panel._persons || []).find((p) => p.entry_id === entryId) || null;
  const name = person ? person.display_name : entryId;
  const data = panel._data[entryId];
  const error = panel._entryErrors[entryId];
  const areas = areasForPerson(person, data);
  const tabs = enabledTabs(areas);

  // Keep the panel state in sync with what is actually rendered: a disabled
  // tab must never stay selected (fall back to the first enabled tab).
  let activeTab = panel._tab;
  if (!tabs.some((tab) => tab.key === activeTab)) {
    activeTab = tabs.length ? tabs[0].key : "";
  }
  panel._tab = activeTab;

  const head = `<div class="person-head"><span class="dot"></span><span>${escapeHtml(name)}</span></div>`;
  const tabBar = tabs.length
    ? `<div class="tabs" role="tablist">${tabs
        .map((tab) => tabButton(activeTab, tab))
        .join("")}</div>`
    : "";

  if (!data) {
    const inner = error
      ? messageHtml(error, true)
      : messageHtml(t("ui_panel_loading_data", "Lade Daten\u2026"), false);
    return `${head}${tabBar}${inner}`;
  }

  const alert = panel._actionError
    ? `<div class="banner" role="alert">\u26A0\uFE0F ${escapeHtml(panel._actionError)}</div>`
    : "";

  let content;
  if (activeTab === "bp") content = bpTab(panel, data, entryId);
  else if (activeTab === "wellbeing") content = wellbeingTab(panel, data, entryId);
  else if (activeTab === "labs") content = labsTab(panel, data, entryId);
  else if (activeTab === "drink") content = drinkTab(panel, data, entryId);
  else {
    content = messageHtml(
      t("ui_panel_no_area", "Für diese Person ist kein Bereich aktiv."),
      false
    );
  }

  return `${head}${tabBar}<div class="views">${alert}${content}</div>`;
}

function tabButton(activeTab, tab) {
  const active = activeTab === tab.key ? " active" : "";
  return `<button class="tab${active}" data-action="tab" data-tab="${tab.key}" type="button" role="tab" aria-selected="${active ? "true" : "false"}">${escapeHtml(
    t(tab.labelKey, tab.label)
  )}</button>`;
}

/* ---- Rückdatierung (REQ-HOM-120) ----------------------------------------- */

/* `datetime-local`-Feld + Schnellwahl „Jetzt"/„Gestern". Der Entwurf des
 * Panels (`_tsDraft`) überlebt Re-Renders; ohne Entwurf startet das Feld auf
 * "jetzt". Ein leeres Feld bedeutet beim Senden ebenfalls "jetzt". */
function tsFieldHtml(panel, field) {
  const draft = panel && panel._tsDraft ? panel._tsDraft[field] : "";
  // Empty = "now" at submit time. A pre-filled value would go stale while the
  // panel stays open (and would silently backdate later reports).
  const value = draft || "";
  const prefix = field.replace(/-ts$/, "");
  const disabled = panel && panel._busy ? " disabled" : "";
  return `<div class="ts-row">
      <label class="field">${escapeHtml(t("ui_panel_ts_label", "Zeitpunkt (leer = jetzt)"))}
        <input type="datetime-local" data-field="${field}" value="${escapeHtml(value)}"
          placeholder="${escapeHtml(t("ui_panel_ts_placeholder", "leer = jetzt"))}" />
      </label>
      <div class="ts-quick">
        <button class="btn ghost" data-action="${prefix}-ts-now" type="button"${disabled}>${escapeHtml(
          t("ui_panel_ts_now", "Jetzt")
        )}</button>
        <button class="btn ghost" data-action="${prefix}-ts-yesterday" type="button"${disabled}>${escapeHtml(
          t("ui_panel_ts_yesterday", "Gestern")
        )}</button>
      </div>
    </div>`;
}

/* ---- Verlauf / Korrekturen (REQ-HOM-115) --------------------------------- */

const DRINK_SOURCE_LABELS = {
  panel: "Panel",
  card: "Karte",
  service: "Service",
  csv: "Import",
  import: "Import",
  automation: "Automation",
};

const DRINK_SOURCE_KEYS = {
  panel: "ui_common_source_panel",
  card: "ui_common_source_card",
  service: "ui_common_source_service",
  csv: "ui_common_source_import",
  import: "ui_common_source_import",
  automation: "ui_common_source_automation",
};

function sourceLabel(value) {
  const raw = String(value == null ? "" : value);
  const key = DRINK_SOURCE_KEYS[raw.toLowerCase()];
  return key ? t(key, DRINK_SOURCE_LABELS[raw.toLowerCase()] || raw) : raw;
}

/* Eintrag eines Verlaufs als eine Zeile; reine Anzeige, alles escaped. */
function historyEntryView(panel, entryId, entry) {
  const when = entry && entry.ts ? entryTime(entry.ts) : "";
  const voided = !!(entry && entry.voided_at);
  return { when, voided };
}

function drinkHistoryText(entry) {
  const parts = [];
  const ml = toNumber(entry.ml, NaN);
  if (Number.isFinite(ml)) parts.push(fmtMl(ml));
  const type = String(entry.type == null ? "" : entry.type).trim();
  if (type) parts.push(type);
  const src = sourceLabel(entry.src);
  if (src) parts.push(src);
  return parts.join(" \u00B7 ");
}

function bpHistoryText(entry) {
  const sys = toNumber(entry.sys, NaN);
  const dia = toNumber(entry.dia, NaN);
  const pulse = toNumber(entry.pulse, NaN);
  const parts = [];
  if (Number.isFinite(sys) && Number.isFinite(dia)) {
    parts.push(`${Math.round(sys)}/${Math.round(dia)}`);
  }
  if (Number.isFinite(pulse)) parts.push(`${Math.round(pulse)} bpm`);
  const note = String(entry.note == null ? "" : entry.note).trim();
  if (note) parts.push(note);
  return parts.join(" \u00B7 ");
}

/* Wohlbefinden-Verlaufseintrag: die History-API liefert nur den Key; Label,
 * Emoji/Bild und Score kommen aus der serverseitigen Skala der Person. */
function wellbeingHistoryView(panel, entryId, entry) {
  const scale = wellbeingScale(panel._data && panel._data[entryId]);
  const key = String(entry && entry.key ? entry.key : "").toLowerCase();
  const index = scale.findIndex((state) => state.key === key);
  const known = index >= 0 ? scale[index] : null;
  const score = entry && entry.score != null ? wellbeingScore(entry) : index >= 0 ? index + 1 : null;
  return {
    emoji: (entry && entry.emoji) || (known && known.emoji) || "\u{1F642}",
    image: (entry && entry.image) || (known && known.image) || "",
    label:
      (entry && entry.key ? t(`ui_common_wb_${String(entry.key).toLowerCase()}`, "") : "") ||
      (entry && entry.label) ||
      (known && known.label) ||
      t("ui_common_unknown", "Keine Angabe"),
    score,
    scoreMax: scale.length || WELLBEING_SCORE_MAX,
  };
}

function historyItemHtml(panel, entryId, kind, entry) {
  if (!entry || typeof entry !== "object") return "";
  const id = entry.id == null ? "" : String(entry.id);
  const { when, voided } = historyEntryView(panel, entryId, entry);
  const confirm = panel._historyConfirm;
  const awaiting =
    !!confirm && confirm.entryId === entryId && confirm.kind === kind && confirm.id === id;

  let body = "";
  if (kind === "drinks") {
    body = `<span class="history-text">${escapeHtml(drinkHistoryText(entry))}</span>`;
  } else if (kind === "blood_pressure") {
    body = `<span class="history-text">${escapeHtml(bpHistoryText(entry))}</span>`;
  } else {
    const view = wellbeingHistoryView(panel, entryId, entry);
    body =
      `${wellbeingVisual({ emoji: view.emoji, image: view.image })}` +
      `<span class="history-text">${escapeHtml(view.label)}${
        view.score != null ? ` \u00B7 ${view.score} / ${view.scoreMax}` : ""
      }</span>`;
  }

  const status = voided
    ? `<span class="status bad" title="${escapeHtml(
        t("ui_panel_voided_title", "Eintrag ist gelöscht (wiederherstellbar)")
      )}">${escapeHtml(t("ui_panel_voided", "gelöscht"))}</span>`
    : "";
  const whenText = when || t("ui_common_no_time", "ohne Zeitangabe");

  let actions = "";
  if (!id) {
    // Altbestand ohne Eintrags-ID: anzeigen, aber nicht korrigierbar.
    actions = "";
  } else if (awaiting) {
    actions = `<div class="history-confirm" role="group" aria-label="${escapeHtml(
      t("ui_panel_void_confirm_aria", "Eintrag löschen bestätigen")
    )}">
        <span>${escapeHtml(t("ui_panel_void_really", "Wirklich löschen?"))}</span>
        <button class="btn" data-action="history-void-confirm" data-kind="${escapeHtml(
          kind
        )}" data-id="${escapeHtml(id)}" type="button"${
          panel._historyBusy ? " disabled" : ""
        }>${escapeHtml(t("ui_common_delete", "Löschen"))}</button>
        <button class="btn ghost" data-action="history-void-cancel" type="button">${escapeHtml(
          t("ui_common_cancel", "Abbrechen")
        )}</button>
      </div>`;
  } else if (voided) {
    actions = `<div class="history-actions">
        <button class="btn ghost" data-action="history-restore" data-kind="${escapeHtml(
          kind
        )}" data-id="${escapeHtml(id)}" type="button" aria-label="${escapeHtml(
          t("ui_panel_restore_aria", "Eintrag vom {when} wiederherstellen", { when: whenText })
        )}"${panel._historyBusy ? " disabled" : ""}>${escapeHtml(
          t("ui_common_restore", "Wiederherstellen")
        )}</button>
      </div>`;
  } else {
    actions = `<div class="history-actions">
        <button class="btn ghost" data-action="history-void" data-kind="${escapeHtml(
          kind
        )}" data-id="${escapeHtml(id)}" type="button" aria-label="${escapeHtml(
          t("ui_panel_void_aria", "Eintrag vom {when} löschen", { when: whenText })
        )}"${panel._historyBusy ? " disabled" : ""}>${escapeHtml(
          t("ui_common_delete", "Löschen")
        )}</button>
      </div>`;
  }

  return `<li class="history-item${voided ? " voided" : ""}" data-history-id="${escapeHtml(id)}">
      <div class="history-main">
        <span class="history-time">${escapeHtml(whenText)}</span>
        ${body}
        ${status}
      </div>
      ${actions}
    </li>`;
}

/* Verlaufsliste eines Tabs inkl. Filter und Inline-Bestätigung. Die Daten
 * kommen ausschließlich aus `health_o_mat/list_history` (kein Zweitweg). */
export function historySection(panel, entryId, kind) {
  if (!entryId) return "";
  const state =
    (panel._history &&
      panel._history[entryId] &&
      panel._history[entryId][kind]) ||
    null;
  const includeVoided = !!(state && state.includeVoided);
  const entries = state && Array.isArray(state.entries)
    ? state.entries.slice(0, HISTORY_LIMIT)
    : [];
  const label = t(HISTORY_KIND_KEYS[kind] || "", HISTORY_KIND_LABELS[kind] || "Verlauf");
  const status = panel._historyStatus && panel._historyStatus.kind === kind
    ? panel._historyStatus
    : null;
  const error = state && state.error ? String(state.error) : "";
  const loading = !!(state && state.loading);

  const count = entries.length === 1
    ? t("ui_panel_history_count_one", "{count} Eintrag", { count: entries.length })
    : t("ui_panel_history_count_other", "{count} Einträge", { count: entries.length });
  const filter = `<div class="history-filter" role="group" aria-label="${escapeHtml(
    t("ui_panel_history_filter_aria", "{label}-Verlauf filtern", { label })
  )}">
      <button class="chip${includeVoided ? "" : " active"}" data-action="history-filter"
        data-kind="${escapeHtml(kind)}" data-voided="0" type="button"
        aria-pressed="${includeVoided ? "false" : "true"}">${escapeHtml(
          t("ui_panel_history_filter_active", "Nur aktive")
        )}</button>
      <button class="chip${includeVoided ? " active" : ""}" data-action="history-filter"
        data-kind="${escapeHtml(kind)}" data-voided="1" type="button"
        aria-pressed="${includeVoided ? "true" : "false"}">${escapeHtml(
          t("ui_panel_history_filter_all", "Auch gelöscht")
        )}</button>
    </div>`;

  const notice = status
    ? `<div class="settings-status ${status.ok ? "ok" : "err"}" role="status">${escapeHtml(
        status.text
      )}</div>`
    : "";
  const errorHtml = error
    ? `<div class="banner" role="alert">\u26A0\uFE0F ${escapeHtml(error)}</div>`
    : "";
  const list = loading
    ? messageHtml(t("ui_panel_history_loading", "Lade Verlauf\u2026"), false)
    : entries.length
      ? `<ul class="history-list">${entries
          .map((entry) => historyItemHtml(panel, entryId, kind, entry))
          .join("")}</ul>`
      : `<div class="muted">${escapeHtml(
          includeVoided
            ? t("ui_panel_history_empty", "Keine Einträge")
            : t("ui_panel_history_empty_active", "Keine Einträge (nur aktive)")
        )}</div>`;

  return `<div class="card" data-history="${escapeHtml(kind)}">
      <div class="history-head">
        <div class="card-title">${escapeHtml(t("ui_panel_history_title", "Verlauf"))}</div>
        <span class="muted">${escapeHtml(count)}</span>
      </div>
      ${filter}
      ${notice}
      ${errorHtml}
      ${list}
    </div>`;
}

/* Undo nur anbieten, wenn die Person aktive Einträge hat (der Entry-Modul-
 * Helper kennt History- und panel_data-Fallback). */
function undoButtonHtml(panel, entryId, kind, label) {
  const available =
    typeof panel._canUndo === "function" ? panel._canUndo(entryId, kind) : false;
  if (!available) return "";
  return `<div class="actions">
      <button class="btn ghost" data-action="undo" data-kind="${escapeHtml(
        kind
      )}" type="button" aria-label="${escapeHtml(label)}"${
        panel._busy ? " disabled" : ""
      }>\u21A9 ${escapeHtml(t("ui_common_undo", "Undo"))}</button>
    </div>`;
}

/* ---- Tab: Trinken (4.2) -------------------------------------------------- */

function drinkTab(panel, data, entryId) {
  const goal = toNumber(data.goal_ml, 0);
  const fallbackMl = toNumber(data.today && data.today.ml, 0);
  const ml = panel._liveNumber(data, "drinks_today", fallbackMl);
  const fallbackPct = goal > 0 ? (ml / goal) * 100 : 0;
  const percent = panel._liveNumber(
    data,
    "percent",
    toNumber(data.today && data.today.percent, fallbackPct)
  );
  const goalText = goal > 0 ? fmtMl(goal) : "\u2013";
  const yesterday = toNumber(data.today && data.today.yesterday_ml, NaN);
  const count = toNumber(data.today && data.today.count, NaN);
  const pace = data.today && data.today.pace;
  const paceInfo = pace ? PACE_INFO[pace] : null;

  const stats = `<div class="tile-stats">
      <div class="kv"><span class="k">${escapeHtml(t("ui_panel_drink_today", "Heute"))}</span><span class="v">${fmtMl(ml)} / ${goalText} (${Math.round(percent)}%)</span></div>
      ${Number.isFinite(yesterday) ? `<div class="kv"><span class="k">${escapeHtml(t("ui_panel_drink_yesterday", "Gestern"))}</span><span class="v">${fmtMl(yesterday)}</span></div>` : ""}
      ${Number.isFinite(count) ? `<div class="kv"><span class="k">${escapeHtml(t("ui_panel_drink_bookings", "Buchungen"))}</span><span class="v">${Math.round(count)}</span></div>` : ""}
      ${paceInfo ? `<div><span class="status ${paceInfo.cls}">${escapeHtml(
        t(paceInfo.textKey, paceInfo.text)
      )}</span></div>` : ""}
    </div>`;

  const quick = QUICK_DRINKS.map(
    (d) => `<button class="btn" data-action="book" data-ml="${d.ml}" data-drink="${escapeHtml(d.type)}" type="button"${panel._busy ? " disabled" : ""}>
        <span>${escapeHtml(d.emoji)} ${escapeHtml(t(d.labelKey, d.label))}</span>
        <span class="ml">${Math.round(d.ml)} ml</span>
      </button>`
  ).join("");

  const formError = panel._formError
    ? `<div class="msg error">${escapeHtml(panel._formError)}</div>`
    : "";

  const canUndo = !(data.undo) || data.undo.drink !== false;
  const undoTitle = escapeHtml(
    t("ui_panel_undo_no_drink_title", "Keine Getränkebuchung zum Rückgängigmachen vorhanden")
  );
  const undo = `<button class="btn ghost" data-action="undo" type="button"${
    panel._busy || !canUndo ? " disabled" : ""
  }${canUndo ? "" : ` title="${undoTitle}"`}${canUndo ? "" : ' aria-disabled="true"'}>\u21A9 ${escapeHtml(
    t("ui_common_undo", "Undo")
  )}</button>`;

  return `
    <div class="card">
      <div class="tile-main">
        ${ringHtml(percent, { sub: `${fmtMl(ml)} / ${goalText}` })}
        ${stats}
      </div>
    </div>
    <div class="card">
      <div class="muted">${escapeHtml(t("ui_panel_drink_quick", "Schnell buchen"))}</div>
      ${tsFieldHtml(panel, "drink-ts")}
      <div class="quick">${quick}</div>
      <form class="freetext" data-form="drink">
        <input type="text" data-field="drink-text" placeholder="${escapeHtml(
          t("ui_panel_drink_placeholder", "z. B. Kaffee 300 ml")
        )}"
          enterkeyhint="done" autocomplete="off" />
        <button class="btn" type="submit"${panel._busy ? " disabled" : ""}>${escapeHtml(
          t("ui_panel_drink_book", "Buchen")
        )}</button>
      </form>
      ${formError}
      ${undo}
    </div>
    ${breakdown(panel, data)}
    ${historySection(panel, entryId, "drinks")}`;
}

function breakdown(panel, data) {
  const map = (data.today && data.today.breakdown) || {};
  const rows = Object.keys(map)
    .map((key) => [key, toNumber(map[key], 0)])
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
      <div class="muted">${escapeHtml(t("ui_panel_drink_breakdown", "Heute nach Getränk"))}</div>
      ${bars}
    </div>`;
}

/* ---- Tab: Blutdruck (4.3) ------------------------------------------------ */

function bpTab(panel, data, entryId) {
  const bp = data.bp || {};
  const sys = panel._liveNumber(data, "bp_sys", toNumber(bp.sys, NaN));
  const dia = panel._liveNumber(data, "bp_dia", toNumber(bp.dia, NaN));
  const pulse = panel._liveNumber(data, "bp_pulse", toNumber(bp.pulse, NaN));
  const categoryKey = panel._liveValue(data, "bp_category", bp.category || "");
  const category = categoryInfo(categoryKey);
  const warn = panel._isWarning(data);
  const hasReading = Number.isFinite(sys) && Number.isFinite(dia);

  const metaParts = [];
  if (Number.isFinite(pulse)) metaParts.push(`${Math.round(pulse)} bpm`);
  if (bp.at) metaParts.push(entryTime(bp.at));

  const head = `<div class="bp-head">
      <div class="bp-big">${hasReading ? `${Math.round(sys)} / ${Math.round(dia)}` : "\u2013 / \u2013"}</div>
      <div class="bp-meta">
        <span>${escapeHtml(t("ui_panel_bp_axis", "systolisch / diastolisch"))}</span>
        ${metaParts.length ? `<span>\u00B7 ${escapeHtml(metaParts.join(" \u00B7 "))}</span>` : ""}
        ${category ? `<span class="status ${category.cls}">${escapeHtml(category.label)}</span>` : ""}
      </div>
    </div>`;

  const avg = bp.avg7 || {};
  const avgParts = [];
  if (avg.sys != null && avg.dia != null) {
    avgParts.push(
      t("ui_panel_bp_avg7", "Ø 7 T: {sys}/{dia}", {
        sys: Math.round(avg.sys),
        dia: Math.round(avg.dia),
      }) + (avg.pulse != null ? ` \u00B7 ${Math.round(avg.pulse)}` : "")
    );
  }
  const avgHtml = avgParts.length
    ? `<div class="kv"><span class="k">${escapeHtml(avgParts[0])}</span></div>`
    : "";

  const warnHtml = warn
    ? `<div class="banner" role="alert">\u26A0\uFE0F ${escapeHtml(
        t("ui_panel_bp_threshold_banner", "Letzte Messung oberhalb der Schwellen")
      )}</div>`
    : "";

  const formError = panel._formError
    ? `<div class="msg error">${escapeHtml(panel._formError)}</div>`
    : "";

  const form = `<form class="card" data-form="bp">
      <div class="muted">${escapeHtml(t("ui_panel_bp_new", "Neue Messung"))}</div>
      ${tsFieldHtml(panel, "bp-ts")}
      <div class="bp-inputs">
        <label class="field">${escapeHtml(t("ui_panel_chart_bp_systolic", "Systolisch"))}
          <input type="number" inputmode="numeric" data-field="sys" min="40" max="300" placeholder="120" />
        </label>
        <label class="field">${escapeHtml(t("ui_panel_chart_bp_diastolic", "Diastolisch"))}
          <input type="number" inputmode="numeric" data-field="dia" min="20" max="200" placeholder="80" />
        </label>
        <label class="field">${escapeHtml(t("ui_panel_bp_pulse", "Puls"))}
          <input type="number" inputmode="numeric" data-field="pulse" min="20" max="250" placeholder="${escapeHtml(
            t("ui_common_optional", "optional")
          )}" />
        </label>
      </div>
      <label class="field">${escapeHtml(t("ui_panel_bp_note", "Notiz"))}
        <input type="text" data-field="note" placeholder="${escapeHtml(
          t("ui_common_optional", "optional")
        )}" autocomplete="off" />
      </label>
      <button class="btn" type="submit"${panel._busy ? " disabled" : ""}>\u{1F4BE} ${escapeHtml(
        t("ui_common_save", "Speichern")
      )}</button>
      ${formError}
    </form>`;

  const undo = undoButtonHtml(
    panel,
    entryId,
    "blood_pressure",
    t("ui_panel_undo_bp", "Letzte Blutdruckmessung rückgängig machen")
  );

  return `<div class="card">${head}${avgHtml}</div>${warnHtml}${form}${undo}${bpHistoryChartHtml(
    bp.entries,
    { title: t("ui_panel_bp_history", "Verlauf systolisch/diastolisch") }
  )}${historySection(panel, entryId, "blood_pressure")}`;
}

/* ---- Tab: Wohlbefinden (4.4) --------------------------------------------- */

/* Attribut der Live-Entity — defensiv: der Panel-Prototyp liefert die
 * Live-Werte ueber `_liveValue`/`_liveNumber`; ein Attributzugriff ist nur
 * moeglich, wenn `_entityOf`/`_state` vorhanden sind (z. B. im Test-Stub
 * nicht). Liefert die Live-Entity das Attribut nicht, bleibt der
 * WS-Snapshot die Quelle. */
function liveAttribute(panel, data, key, attribute) {
  if (!panel || typeof panel._entityOf !== "function" || typeof panel._state !== "function") {
    return "";
  }
  const entityId = panel._entityOf(data, key);
  if (!entityId) return "";
  const state = panel._state(entityId);
  const attributes = state && state.attributes;
  if (!attributes) return "";
  const value = attributes[attribute];
  return value == null ? "" : String(value);
}

export function wellbeingView(panel, data) {
  const wb = (data && data.wellbeing) || {};
  const live = panel._liveValue(data, "wellbeing", undefined);
  // entities.wellbeing is a timestamp sensor; its state is the timestamp of
  // the last report — NOT a wellbeing key. The key always comes from the
  // (server-localised) payload.
  const key = String(wb.key || "").toLowerCase();
  const scale = wellbeingScale(data);
  const known = scale.find((s) => s.key === key);
  // Score (1…N): Live-Entity, sonst Server-Feld, sonst aus dem Key
  // abgeleitet (älterer Payload ohne `score`).
  const liveScore =
    typeof panel._liveNumber === "function"
      ? panel._liveNumber(data, "wellbeing_score", NaN)
      : NaN;
  const score =
    Number.isFinite(liveScore) && liveScore >= 1 && liveScore <= WELLBEING_SCORE_MAX
      ? Math.round(liveScore)
      : wellbeingScore(wb);
  /* Label/Emoji LIVE-FIRST: liefert die Live-Entity (`entities.wellbeing`)
   * die Attribute `label`/`emoji`, sind diese aktueller als der
   * (moeglicherweise veralteten) WS-Snapshot — sonst wuerde die Kopfzeile
   * einen veralteten Text neben dem aktuellen Score zeigen. Liefert die
   * Live-Entity keine Attribute, bleibt der Snapshot die Quelle. */
  const liveLabel = liveAttribute(panel, data, "wellbeing", "label");
  const liveEmoji = liveAttribute(panel, data, "wellbeing", "emoji");
  const liveImage = liveAttribute(panel, data, "wellbeing", "image");
  const rawLabel =
    liveLabel || wb.label || (known && known.label) || t("ui_common_unknown", "Keine Angabe");
  return {
    key,
    emoji: liveEmoji || wb.emoji || (known && known.emoji) || "\u{1F642}",
    image: liveImage || wb.image || (known && known.image) || "",
    /* Server labels are German; translate by the canonical state key. */
    label: key ? t(`ui_common_wb_${key}`, rawLabel) : rawLabel,
    at: wb.at || (typeof live === "string" && live !== "unknown" ? live : ""),
    // Numerischer Score (1…N); null ohne Meldung (REQ-HOM-112).
    score,
  };
}

function wellbeingTab(panel, data, entryId) {
  const view = wellbeingView(panel, data);
  const scale = wellbeingScale(data);
  const scoreMax = scale.length || WELLBEING_SCORE_MAX;
  /* Bestätigungsmodus (REQ-HOM-114): Auswahl erst vormerken, senden erst der
   * „Übernehmen"-Button. Ohne Pending bleibt alles wie bisher. */
  const confirm = !!(data && data.wellbeing_confirm === true);
  const pending = panel._wbPending && panel._wbPending.entryId === entryId
    ? panel._wbPending
    : null;
  const pendingIndex = pending
    ? pending.key
      ? scale.findIndex((state) => state.key === pending.key)
      : Number.isInteger(pending.score)
        ? pending.score - 1
        : -1
    : -1;
  const pendingState = pendingIndex >= 0 ? scale[pendingIndex] : null;
  const stagedKey = confirm && pendingState ? pendingState.key : "";
  const pendingScore =
    pending && pending.score != null
      ? pending.score
      : pendingIndex >= 0
        ? pendingIndex + 1
        : null;
  const buttons = scale.map(
    (s) => `<button class="wb-btn${s.key === view.key ? " active" : ""}${
      s.key === stagedKey ? " pending" : ""
    }" data-action="wb" data-key="${s.key}" type="button"${panel._busy ? " disabled" : ""}>
        ${wellbeingVisual(s)}
        <span class="lbl">${escapeHtml(s.label)}</span>
      </button>`
  ).join("");

  const pendingScoreText = pendingScore != null && pendingScore > 0
    ? ` (${pendingScore} / ${scoreMax})`
    : "";
  const confirmRow = confirm && pendingState
    ? `<div class="wb-confirm">
        <span class="wb-pending-hint">${escapeHtml(
          t("ui_panel_wb_confirm_hint", "Ausgewählt: {label}{score} – noch nicht übernommen", {
            label: pendingState.label,
            score: pendingScoreText,
          })
        )}</span>
        <button class="btn" data-action="wb-confirm" type="button"${panel._busy ? " disabled" : ""}>${escapeHtml(
          t("ui_panel_wb_confirm", "Übernehmen")
        )}</button>
      </div>`
    : "";

  const at = view.at ? entryTime(view.at) : "";
  const scoreText =
    view.score != null ? ` \u00B7 ${view.score} / ${scoreMax}` : "";
  const last = `<div class="tile-row">
      ${wellbeingVisual(view)}
      <span>${escapeHtml(t("ui_panel_wb_last", "Zuletzt:"))} <strong>${escapeHtml(view.label)}</strong>${scoreText}</span>
      ${at ? `<span class="muted">\u00B7 ${escapeHtml(at)}</span>` : ""}
    </div>`;

  const scoreFormError = panel._formError
    ? `<div class="msg error">${escapeHtml(panel._formError)}</div>`
    : "";
  const scoreForm = `<form class="card" data-form="wellbeing">
      <div class="muted">${escapeHtml(
        t("ui_panel_wb_numeric", "Alternativ als Zahl (1–{max})", { max: scoreMax })
      )}</div>
      <div class="bp-inputs">
        <label class="field">${escapeHtml(t("ui_panel_wb_value", "Wert"))}
          <input type="number" inputmode="numeric" data-field="wb-score" min="1" max="${scoreMax}" step="1" placeholder="1\u2013${scoreMax}" />
        </label>
        <button class="btn" type="submit"${panel._busy ? " disabled" : ""}>\u{1F4BE} ${escapeHtml(
          t("ui_panel_wb_report", "Melden")
        )}</button>
      </div>
      ${scoreFormError}
    </form>`;

  /* Einzige Verlaufsquelle ist die History-API (`historySection`, REQ-HOM-115)
   * — `wellbeing.history` speist nur noch den Score-Chart, damit die Liste
   * nicht doppelt gerendert wird. */
  const history = Array.isArray(data.wellbeing && data.wellbeing.history)
    ? data.wellbeing.history
    : [];

  const undo = undoButtonHtml(
    panel,
    entryId,
    "wellbeing",
    t("ui_panel_undo_wb", "Letzte Wohlbefinden-Meldung rückgängig machen")
  );

  /* Score-Chart (REQ-HOM-112): Linienchart des Verlaufs, Y-Achse 1…N,
   * aktueller Wert hervorgehoben. Leerer Verlauf -> Hinweis statt Chart.
   * `current` = aktueller Wohlbefinden-Block: die Historie endet mit dem
   * abgelösten Status, der aktuelle Wert steht nur im Block selbst — ohne ihn
   * würde der Chart den alten Wert als "aktuell" markieren.
   *
   * EINE Quelle fuer den Score UND das Label: der Chart bekommt den bereits
   * aufgeloesten `view` (Live-Entity, sonst Server-Feld) und NICHT die
   * `panel_data`-Momentaufnahme — sonst zeigten Kopfzeile und Chart bei
   * einem Report von ausserhalb des Panels (Select-Entity, Automation,
   * Dashboard) verschiedene Werte (Snapshot "2" vs. Live "4"). */
  const chartHtml = wellbeingChartHtml(history, {
    current: {
      ...data.wellbeing,
      label: view.label,
      emoji: view.emoji,
      image: view.image,
      score: view.score,
    },
    scale,
    title: t("ui_panel_chart_wb_title", "Score-Verlauf"),
  });

  return `<div class="card">
      <div class="muted">${escapeHtml(t("ui_panel_wb_question", "Wie geht es dir?"))}</div>
      ${tsFieldHtml(panel, "wb-ts")}
      <div class="wb-row">${buttons}</div>
      ${confirmRow}
      ${last}
      ${undo}
    </div>${scoreForm}${chartHtml}${historySection(panel, entryId, "wellbeing")}`;
}

/* ---- Tab: Laborwerte (REQ-HOM-122) ---------------------------------------- */

/* Marker ausserhalb des Referenzbereichs ueber alle SICHTBAREN Kategorien
 * (`hidden`-Kategorien ausgenommen) — reine Darstellungslogik auf den bereits
 * geladenen `panel_data`-Attributen, kein zusaetzlicher Request (§7.3). */
function _labWarningCount(data) {
  const labs = (data && data.labs) || { categories: [], markers: {} };
  const hiddenCategories = new Set(
    (labs.categories || [])
      .filter((category) => category && category.hidden)
      .map((category) => category.key)
  );
  return Object.values(labs.markers || {}).filter(
    (marker) => marker && !hiddenCategories.has(marker.category) && marker.in_range === false
  ).length;
}

/* Kontextbezogener Medizin-Hinweis (§8, REQ-HOM-125). Zustand kommt
 * ausschließlich aus `panel_data` — `get_settings` ist admin-only und wäre für
 * Nicht-Admins leer. Fehlendes Feld = sichtbar. */
function labDisclaimerHtml() {
  return `<div class="labs-disclaimer" role="note">${escapeHtml(
    t(
      "ui_panel_lab_disclaimer",
      "⚠️ Hinweis: keine medizinische Beratung — Richtwerte, keine Diagnose. Referenzbereiche in den Einstellungen anpassen."
    )
  )}</div>`;
}

/* Kategorien, die im Tab erscheinen: nicht ausgeblendet UND mit mindestens
 * einem Marker (Katalog oder Custom) — sonst entstuende eine leere Leiste. */
function visibleLabCategories(labs) {
  const markers = Object.values((labs && labs.markers) || {});
  return ((labs && labs.categories) || []).filter((category) => {
    if (!category || category.hidden) return false;
    return markers.some((marker) => marker && marker.category === category.key);
  });
}

/* Kategorie-Leiste mit ‹/›-Knoepfen; der aktive Eintrag ist per
 * `aria-selected` markiert (role=tablist). */
function labCategoryBar(labs, activeCategory) {
  const categories = visibleLabCategories(labs);
  if (!categories.length) return "";
  return `<div class="lab-category-bar" role="tablist">
      <button class="btn ghost" type="button" data-action="lab-category-prev" aria-label="${escapeHtml(
        t("ui_panel_lab_prev", "Vorherige Kategorie")
      )}">\u2039</button>
      ${categories
        .map(
          (category) =>
            `<button class="lab-category${category.key === activeCategory ? " active" : ""}" type="button" data-action="lab-category" data-category="${escapeHtml(
              category.key
            )}" role="tab" aria-selected="${category.key === activeCategory ? "true" : "false"}">${escapeHtml(
              labDisplayName(category, category.key)
            )}</button>`
        )
        .join("")}
      <button class="btn ghost" type="button" data-action="lab-category-next" aria-label="${escapeHtml(
        t("ui_panel_lab_next", "Nächste Kategorie")
      )}">\u203A</button>
    </div>`;
}

/* Ein Marker mit Wert, Badge, Eingabe-Subzeile und Verlaufsgraph. `value`
 * und `unit` sind Nutzerdaten und laufen durch `escapeHtml`. */
function labMarkerRow(marker, markerKey) {
  const value =
    marker && marker.value != null
      ? `${escapeHtml(marker.value)} ${escapeHtml(marker.unit)}`
      : "\u2013";
  return `<div class="lab-row" data-marker="${escapeHtml(markerKey)}">
      <div class="lab-row-main">
        <span class="lab-row-name">${escapeHtml(labDisplayName(marker, markerKey))}</span>
        <span class="lab-row-value">${value}</span>
        ${labBadge(marker.in_range)}
      </div>
      ${labReportedSubline(marker)}
      ${labChartHtml(marker.history, {
        title: "",
        refMin: marker.ref_min,
        refMax: marker.ref_max,
      })}
    </div>`;
}

/* Speichern des Erfassungs-Formulars. Der Tab liegt in diesem Modul, der
 * Panel-Klick-Switch liegt in `health-o-mat-panel.js`; deshalb haengt der
 * Handler an der eigenen Delegation (siehe `ensureLabGestures`). */
async function submitLabValue(panel, entryId) {
  if (!panel || !entryId || panel._busy || typeof panel._ws !== "function") return;
  const read = (field) => {
    const el = panel.shadowRoot.querySelector(`[data-field="${field}"]`);
    return el && el.value != null ? String(el.value).trim() : "";
  };
  const marker = read("lab-add-marker");
  const rawValue = read("lab-add-value");
  const value = toNumber(rawValue, NaN);
  if (!marker || !rawValue || !Number.isFinite(value)) {
    panel._formError = t(
      "ui_panel_val_lab_value",
      "Bitte Marker und einen numerischen Wert angeben."
    );
    panel._render();
    return;
  }
  const unit = read("lab-add-unit");
  const reportRef = read("lab-add-report-ref");

  panel._busy = true;
  panel._actionError = null;
  panel._formError = null;
  panel._render();
  try {
    const message = { type: WS.addLabValue, entry_id: entryId, marker, value };
    if (unit) message.unit = unit;
    if (reportRef) message.report_ref = reportRef;
    await panel._ws(message);
    await panel._reloadEntry(entryId);
  } catch (err) {
    panel._actionError = errMsg(err);
  } finally {
    panel._busy = false;
    panel._render();
  }
}

/* ---- Laborbericht (REQ-HOM-123) ------------------------------------------
 *
 * Panel-lokale Zweitimplementierung des Dialogs (§6.3): die Karte ist
 * standalone; ein Shared-Modul lohnte erst beim dritten Konsumenten.
 */

const LAB_REPORT_MAX_ROWS_UI = 60;

function emptyLabReportRow() {
  return { marker: "", value: "", unit: "" };
}

function labReportDraft(panel, entryId) {
  // Defensiv: Panel-Instanzen überleben Hot-Reloads nicht garantiert (§6.3).
  const existing = panel._labReportDraft && panel._labReportDraft[entryId];
  if (existing) return existing;
  if (!panel._labReportDraft) panel._labReportDraft = {};
  panel._labReportDraft[entryId] = { ts: "", reportRef: "", rows: [emptyLabReportRow()] };
  return panel._labReportDraft[entryId];
}

function collectLabReportDraft(panel, entryId) {
  const draft = labReportDraft(panel, entryId);
  const read = (field) => {
    const el = panel.shadowRoot.querySelector(`[data-field="${field}"]`);
    return el && el.value != null ? String(el.value) : "";
  };
  draft.ts = read("lab-report-ts");
  draft.reportRef = read("lab-report-ref");
  draft.rows = draft.rows.map((_row, index) => ({
    marker: read(`lab-report-marker-${index}`),
    value: read(`lab-report-value-${index}`),
    unit: read(`lab-report-unit-${index}`),
  }));
  return draft;
}

function validLabReportTs(raw) {
  const value = String(raw || "").trim();
  if (!value) return { iso: "" };
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) {
    return { error: t("ui_panel_lab_report_ts", "Zeitpunkt") + ": ungültig" };
  }
  return { iso: parsed.toISOString() };
}

function reportMarkerOptions(markers, selectedKey) {
  const placeholder = selectedKey
    ? ""
    : `<option value="" selected>${escapeHtml(
        t("ui_panel_lab_marker_choose", "— bitte wählen —")
      )}</option>`;
  return `${placeholder}${labMarkerOptionsHtml(markers, selectedKey)}`;
}

function unitOptions(marker, selectedUnit) {
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
  return `${options}<option value="__custom__"${
    current === "__custom__" ? " selected" : ""
  }>${escapeHtml(t("ui_panel_lab_unit_custom", "Andere …"))}</option>`;
}

function labReportRowHtml(markers, row, index, entryId) {
  const marker = markers[row.marker];
  return `<div class="lab-report-row">
      <select data-field="lab-report-marker-${index}" aria-label="${escapeHtml(
        t("ui_panel_lab_marker", "Marker")
      )}">${reportMarkerOptions(markers, row.marker)}</select>
      <input type="number" step="any" inputmode="decimal"
        data-field="lab-report-value-${index}" aria-label="${escapeHtml(
          t("ui_panel_lab_value_field", "Wert")
        )}" value="${attrValue(row.value)}" />
      <select data-field="lab-report-unit-pick-${index}" aria-label="${escapeHtml(
        t("ui_panel_lab_unit_field", "Einheit (optional)")
      )}">${unitOptions(marker, row.unit)}</select>
      <input type="text" data-field="lab-report-unit-${index}" aria-label="${escapeHtml(
        t("ui_panel_lab_unit_field", "Einheit (optional)")
      )}" value="${attrValue(row.unit)}" placeholder="${escapeHtml(
        (marker && marker.unit) || t("ui_common_optional", "optional")
      )}" autocomplete="off" />
      <button class="btn ghost" type="button" data-action="lab-report-remove"
        data-entry="${escapeHtml(entryId)}" data-index="${index}" aria-label="${escapeHtml(
          t("ui_panel_lab_report_remove_row", "Zeile entfernen")
        )}">\u2715</button>
    </div>`;
}

export function labReportForm(panel, labs, entryId) {
  // Ohne Marker gibt es nichts zu erfassen — kein leerer Dialog (Parität zur Karte).
  const markers = labs.markers || {};
  if (!Object.keys(markers).length) return "";
  const draft = labReportDraft(panel, entryId);
  const atLimit = draft.rows.length >= LAB_REPORT_MAX_ROWS_UI;
  const disabled = panel._busy ? " disabled" : "";
  const addDisabled = panel._busy || atLimit ? " disabled" : "";
  const rows = draft.rows
    .map((row, index) => labReportRowHtml(markers, row, index, entryId))
    .join("");
  const note = atLimit
    ? `<div class="muted">${escapeHtml(
        t("ui_panel_lab_report_limit", "Höchstens 60 Zeilen pro Bericht.")
      )}</div>`
    : "";
  // Offen-Zustand ueberlebt die Re-Renders bei strukturellen Aenderungen
  // (Zeile anlegen/entfernen, Marker/Einheit wechseln) — sonst klappt der
  // Dialog bei jedem Klick zu (E2E-Befund Batch-Dialog).
  const open = panel._labReportOpen && panel._labReportOpen[entryId] ? " open" : "";
  return `<details class="lab-report-form" data-entry="${escapeHtml(entryId)}"${open}>
      <summary>${escapeHtml(t("ui_panel_lab_report_title", "Laborbericht erfassen"))}</summary>
      <div class="lab-report-fill">
        <button class="btn ghost" type="button" data-action="lab-report-fill-visible"
          data-entry="${escapeHtml(entryId)}"${disabled}>${escapeHtml(
            t("ui_panel_lab_fill_visible", "Alle sichtbaren Marker anlegen")
          )}</button>
        <button class="btn ghost" type="button" data-action="lab-report-fill-last"
          data-entry="${escapeHtml(entryId)}"${disabled}>${escapeHtml(
            t("ui_panel_lab_fill_last", "Zuletzt verwendete Marker anlegen")
          )}</button>
      </div>
      <label class="field">${escapeHtml(t("ui_panel_lab_report_ts", "Zeitpunkt"))}
        <input type="datetime-local" data-field="lab-report-ts" value="${attrValue(draft.ts)}" />
      </label>
      <label class="field">${escapeHtml(
        t("ui_panel_lab_report_ref", "Bericht-Link/ID (optional)")
      )}
        <input type="text" data-field="lab-report-ref" value="${attrValue(draft.reportRef)}"
          placeholder="${escapeHtml(t("ui_common_optional", "optional"))}" autocomplete="off" />
      </label>
      <div class="lab-report-rows">${rows}</div>
      ${note}
      <div class="lab-report-actions">
        <button class="btn ghost" type="button" data-action="lab-report-add"
          data-entry="${escapeHtml(entryId)}"${addDisabled}>＋ ${escapeHtml(
            t("ui_panel_lab_report_add_row", "Zeile")
          )}</button>
        <button class="btn" type="button" data-action="lab-report-save"
          data-entry="${escapeHtml(entryId)}"${disabled}>\u{1F4BE} ${escapeHtml(
            t("ui_panel_lab_report_save", "Bericht speichern")
          )}</button>
      </div>
    </details>`;
}

export function handleLabReportChange(panel, entryId, field, value) {
  if (!entryId || !field || !field.startsWith("lab-report-")) return false;
  const draft = labReportDraft(panel, entryId);
  if (field === "lab-report-ts") {
    draft.ts = value;
    return false;
  }
  if (field === "lab-report-ref") {
    draft.reportRef = value;
    return false;
  }
  const markerMatch = /^lab-report-marker-(\d+)$/.exec(field);
  if (markerMatch) {
    const row = draft.rows[Number(markerMatch[1])];
    if (!row) return false;
    row.marker = value;
    row.unit = ""; // Einheiten-Dropdown hängt am Marker
    return true;
  }
  const pickMatch = /^lab-report-unit-pick-(\d+)$/.exec(field);
  if (pickMatch) {
    const row = draft.rows[Number(pickMatch[1])];
    if (!row) return false;
    row.unit = value === "__custom__" ? "" : value;
    return true;
  }
  const unitMatch = /^lab-report-unit-(\d+)$/.exec(field);
  if (unitMatch) {
    const row = draft.rows[Number(unitMatch[1])];
    if (row) row.unit = value;
    return false;
  }
  const valueMatch = /^lab-report-value-(\d+)$/.exec(field);
  if (valueMatch) {
    const row = draft.rows[Number(valueMatch[1])];
    if (row) row.value = value;
    return false;
  }
  return false;
}

export function addLabReportRow(panel, entryId) {
  const draft = collectLabReportDraft(panel, entryId);
  if (draft.rows.length >= LAB_REPORT_MAX_ROWS_UI) return;
  draft.rows.push(emptyLabReportRow());
  panel._render();
}

function removeLabReportRow(panel, entryId, index) {
  const draft = collectLabReportDraft(panel, entryId);
  if (!Number.isInteger(index) || draft.rows.length <= 1) return;
  draft.rows.splice(index, 1);
  panel._render();
}

export function fillLabReportDraft(panel, entryId, mode) {
  const draft = collectLabReportDraft(panel, entryId);
  const data = (panel._data || {})[entryId] || {};
  const labs = data.labs || { categories: [], markers: {} };
  const markers = labs.markers || {};
  let keys = [];
  if (mode === "visible") {
    const visible = new Set(visibleLabCategories(labs).map((category) => category.key));
    keys = Object.keys(markers).filter((key) => visible.has(markers[key].category));
  } else {
    const last = labs.last_report || {};
    keys = (Array.isArray(last.marker_keys) ? last.marker_keys : []).filter(
      (key) => markers[key]
    );
  }
  const used = new Set(draft.rows.map((row) => row.marker).filter(Boolean));
  for (const key of keys) {
    if (used.has(key)) continue;
    const empty = draft.rows.find((row) => !row.marker && !row.value && !row.unit);
    if (empty) {
      empty.marker = key;
    } else if (draft.rows.length < LAB_REPORT_MAX_ROWS_UI) {
      draft.rows.push({ marker: key, value: "", unit: "" });
    } else {
      break;
    }
    used.add(key);
  }
  panel._render();
}

async function submitLabReport(panel, entryId) {
  if (!panel || !entryId || panel._busy || typeof panel._ws !== "function") return;
  const draft = collectLabReportDraft(panel, entryId);
  const ts = validLabReportTs(draft.ts);
  if (ts.error) {
    panel._formError = ts.error;
    panel._render();
    return;
  }
  const values = [];
  for (const row of draft.rows) {
    const marker = String(row.marker || "").trim();
    const rawValue = String(row.value || "").trim().replace(",", ".");
    const unit = String(row.unit || "").trim();
    if (!marker && !rawValue && !unit) continue;
    if (!marker || !/^-?\d+(\.\d+)?$/.test(rawValue)) {
      panel._formError = t(
        "ui_panel_val_lab_value",
        "Bitte Marker und einen numerischen Wert angeben."
      );
      panel._render();
      return;
    }
    values.push(
      unit
        ? { marker, value: Number(rawValue), unit }
        : { marker, value: Number(rawValue) }
    );
  }
  if (!values.length) {
    panel._formError = t(
      "ui_panel_lab_report_empty",
      "Bitte mindestens einen Wert erfassen."
    );
    panel._render();
    return;
  }
  const message = { type: WS.addLabReport, entry_id: entryId, values };
  if (ts.iso) message.ts = ts.iso;
  if (String(draft.reportRef || "").trim()) {
    message.report_ref = String(draft.reportRef).trim();
  }

  panel._busy = true;
  panel._actionError = null;
  panel._formError = null;
  panel._render();
  try {
    const result = await panel._ws(message);
    const failure = resultError(result);
    if (failure) {
      panel._formError = failure;
      return;
    }
    // ts/reportRef bleiben stehen (§6.4) — nur Werte + Zeilen werden geleert.
    panel._labReportDraft[entryId] = { ...draft, rows: [emptyLabReportRow()] };
    // Der Dialog startet nach dem Absenden wieder im Startzustand (zugeklappt).
    if (panel._labReportOpen) panel._labReportOpen[entryId] = false;
    await panel._reloadEntry(entryId);
  } catch (err) {
    panel._formError = errMsg(err);
  } finally {
    panel._busy = false;
    panel._render();
  }
}

/* Envelope-Fehler der Batch-Kommandos (§3): `panel._ws` löst bei
 * {"ok": false} nicht ab. */
function resultError(result) {
  if (!result || result.ok !== false) return "";
  const error = result.error && typeof result.error === "object" ? result.error : {};
  return error.message || error.code || t("ui_panel_lab_report_empty", "Fehler");
}

/* Kategorie schrittweise wechseln (Knoepfe + Wischgeste). Faellt die gemerkte
 * Kategorie weg (Flaeche neu konfiguriert), beginnt die Suche beim ersten
 * sichtbaren Eintrag. */
function stepLabCategory(panel, direction) {
  if (!panel) return;
  const data = (panel._data || {})[panel._selectedEntry];
  const categories = visibleLabCategories((data && data.labs) || {});
  if (!categories.length) return;
  const index = categories.findIndex((category) => category.key === panel._labCategory);
  const next =
    index < 0 ? 0 : (index + direction + categories.length) % categories.length;
  panel._labCategory = categories[next].key;
  if (typeof panel._render === "function") panel._render();
}

/* Swipe + Klick-Delegation EINMAL je Panel-Element registrieren. Bewusst ohne
 * Gesture-Library: horizontales Delta-X ab Schwelle, `passive`-Listener, damit
 * vertikales Scrollen und die bestehenden Tab-Gesten unberuehrt bleiben. */
const LAB_GESTURES_INSTALLED = "__homLabGesturesInstalled";
const LAB_SWIPE_THRESHOLD = 40;

function ensureLabGestures(panel) {
  if (!panel || panel[LAB_GESTURES_INSTALLED]) return;
  const root = panel.shadowRoot;
  if (!root || typeof root.addEventListener !== "function") return;
  panel[LAB_GESTURES_INSTALLED] = true;

  // `toggle` bubbelt nicht — Capture-Phase faengt es trotzdem am Shadow-Root
  // ab. Der Offen-Zustand wird pro Entry gemerkt, damit `labReportForm` ihn
  // nach einem Re-Render wieder auf das `open`-Attribut abbilden kann.
  root.addEventListener(
    "toggle",
    (ev) => {
      const target = ev.target;
      if (!target || typeof target.closest !== "function") return;
      const form = target.closest("details.lab-report-form");
      if (!form) return;
      const entryId = form.getAttribute("data-entry") || "";
      if (!entryId) return;
      if (!panel._labReportOpen) panel._labReportOpen = {};
      panel._labReportOpen[entryId] = form.open === true;
    },
    true
  );

  let startX = null;
  let startY = null;
  root.addEventListener(
    "touchstart",
    (ev) => {
      const touch = ev.touches && ev.touches[0];
      startX = touch ? touch.clientX : null;
      startY = touch ? touch.clientY : null;
    },
    { passive: true }
  );
  root.addEventListener(
    "touchend",
    (ev) => {
      if (startX == null) return;
      const touch = ev.changedTouches && ev.changedTouches[0];
      const fromX = startX;
      const fromY = startY == null ? null : startY;
      startX = null;
      startY = null;
      if (!touch) return;
      // Nur im Detail-View auf dem Laborwerte-Tab — andere Tabs haben kein
      // Kategorie-Konzept.
      if (panel._view && panel._view !== "detail") return;
      if (panel._tab !== "labs") return;
      // Eingabefelder (Zahl/Slider) nie als Wischflaeche interpretieren.
      const target = ev.target;
      if (target && typeof target.closest === "function" && target.closest("input, select, textarea")) {
        return;
      }
      const deltaX = touch.clientX - fromX;
      const deltaY = fromY == null ? 0 : touch.clientY - fromY;
      if (Math.abs(deltaX) < LAB_SWIPE_THRESHOLD) return;
      // Vertikales Scrollen nie kapern: nur klar horizontale Gesten.
      if (Math.abs(deltaY) > Math.abs(deltaX)) return;
      stepLabCategory(panel, deltaX < 0 ? 1 : -1);
    },
    { passive: true }
  );
  root.addEventListener("click", (ev) => {
    const target = ev.target;
    if (!target || typeof target.closest !== "function") return;
    const categoryEl = target.closest('[data-action^="lab-category"]');
    if (categoryEl) {
      const action = categoryEl.getAttribute("data-action");
      if (action === "lab-category") {
        panel._labCategory = categoryEl.getAttribute("data-category");
        if (typeof panel._render === "function") panel._render();
      } else if (action === "lab-category-prev") {
        stepLabCategory(panel, -1);
      } else if (action === "lab-category-next") {
        stepLabCategory(panel, 1);
      }
      return;
    }
    const fillVisibleEl = target.closest('[data-action="lab-report-fill-visible"]');
    if (fillVisibleEl) {
      fillLabReportDraft(panel, fillVisibleEl.getAttribute("data-entry") || "", "visible");
      return;
    }
    const fillLastEl = target.closest('[data-action="lab-report-fill-last"]');
    if (fillLastEl) {
      fillLabReportDraft(panel, fillLastEl.getAttribute("data-entry") || "", "last");
      return;
    }
    const reportAddEl = target.closest('[data-action="lab-report-add"]');
    if (reportAddEl) {
      addLabReportRow(panel, reportAddEl.getAttribute("data-entry") || "");
      return;
    }
    const reportRemoveEl = target.closest('[data-action="lab-report-remove"]');
    if (reportRemoveEl) {
      removeLabReportRow(
        panel,
        reportRemoveEl.getAttribute("data-entry") || "",
        Number(reportRemoveEl.getAttribute("data-index"))
      );
      return;
    }
    const discardEl = target.closest('[data-action="lab-report-discard"]');
    if (discardEl) {
      discardLabReport(panel, discardEl.getAttribute("data-entry") || "");
      return;
    }
    const reportSaveEl = target.closest('[data-action="lab-report-save"]');
    if (reportSaveEl) {
      submitLabReport(panel, reportSaveEl.getAttribute("data-entry") || "");
      return;
    }
    const saveEl = target.closest('[data-action="lab-add-value"]');
    if (saveEl) submitLabValue(panel, saveEl.getAttribute("data-entry") || "");
  });
}

export function labReportDiscardHtml(panel, labs, entryId) {
  const last = labs && labs.last_report;
  if (!last || !last.ts) return "";
  const count = Array.isArray(last.marker_keys) ? last.marker_keys.length : 0;
  return `<div class="lab-report-discard">
      <button class="btn ghost" type="button" data-action="lab-report-discard"
        data-entry="${escapeHtml(entryId)}"${panel._busy ? " disabled" : ""}>${escapeHtml(
          `${t("ui_panel_lab_report_discard", "Diesen Bericht verwerfen")} (${count})`
        )}</button>
    </div>`;
}

async function discardLabReport(panel, entryId) {
  if (!panel || !entryId || panel._busy || typeof panel._ws !== "function") return;
  const last = (((panel._data || {})[entryId] || {}).labs || {}).last_report;
  if (!last || !last.ts) return;
  const count = Array.isArray(last.marker_keys) ? last.marker_keys.length : 0;
  const confirmed =
    typeof window !== "undefined" && typeof window.confirm === "function"
      ? window.confirm(
          t(
            "ui_panel_lab_report_discard_confirm",
            "Diesen Bericht mit {count} Werten verwerfen?",
            { count }
          )
        )
      : true;
  if (!confirmed) return;
  const message = { type: WS.removeLabReport, entry_id: entryId, ts: last.ts };
  if (last.report_ref) message.report_ref = last.report_ref;

  panel._busy = true;
  panel._actionError = null;
  panel._formError = null;
  panel._render();
  try {
    const result = await panel._ws(message);
    const failure = resultError(result);
    if (failure) {
      panel._formError = failure;
      return;
    }
    await panel._reloadEntry(entryId);
  } catch (err) {
    panel._formError = errMsg(err);
  } finally {
    panel._busy = false;
    panel._render();
  }
}

export function labsTab(panel, data, entryId) {
  ensureLabGestures(panel);
  const labs = (data && data.labs) || { categories: [], markers: {} };
  const categories = visibleLabCategories(labs);
  const disclaimer =
    data && data.lab_hide_panel_disclaimer === true ? "" : labDisclaimerHtml();
  if (!categories.length) {
    // "Alle ausgeblendet" ist ein Zustand der Einstellungen, "keine
    // Kategorien" ein Zustand des Katalogs — der Text unterscheidet das (§8).
    const allHidden = Array.isArray(labs.categories) && labs.categories.length > 0;
    const emptyText = allHidden
      ? t("ui_panel_lab_all_hidden", "Alle Kategorien ausgeblendet")
      : t("ui_panel_lab_no_categories", "Keine Laborwert-Kategorie sichtbar.");
    return `${disclaimer}${messageHtml(emptyText, false)}`;
  }
  let active = panel._labCategory;
  if (!categories.some((category) => category.key === active)) {
    active = categories[0].key;
  }
  panel._labCategory = active;

  const markersInCategory = Object.entries(labs.markers || {}).filter(
    ([, marker]) => marker && marker.category === active
  );
  const rows = markersInCategory
    .map(([key, marker]) => labMarkerRow(marker, key))
    .join("");

  const formError = panel._formError
    ? `<div class="msg error">${escapeHtml(panel._formError)}</div>`
    : "";
  const disabled = panel._busy ? " disabled" : "";
  const entryForm = `<details class="lab-entry-form">
      <summary>${escapeHtml(t("ui_panel_lab_add_value", "Neuen Wert erfassen"))}</summary>
      <label class="field">${escapeHtml(t("ui_panel_lab_marker", "Marker"))}
        <select data-field="lab-add-marker">${labMarkerOptionsHtml(labs.markers, null)}</select>
      </label>
      <label class="field">${escapeHtml(t("ui_panel_lab_value_field", "Wert"))}
        <input type="number" step="any" data-field="lab-add-value" />
      </label>
      <label class="field">${escapeHtml(t("ui_panel_lab_unit_field", "Einheit (optional)"))}
        <input type="text" data-field="lab-add-unit" placeholder="${escapeHtml(
          t("ui_common_optional", "optional")
        )}" autocomplete="off" />
      </label>
      <label class="field">${escapeHtml(t("ui_panel_lab_report_ref", "Bericht-Link/ID (optional)"))}
        <input type="text" data-field="lab-add-report-ref" placeholder="${escapeHtml(
          t("ui_common_optional", "optional")
        )}" autocomplete="off" />
      </label>
      <button class="btn" type="button" data-action="lab-add-value" data-entry="${escapeHtml(
        entryId
      )}"${disabled}>\u{1F4BE} ${escapeHtml(t("ui_panel_lab_save", "Speichern"))}</button>
    </details>`;
  const reportForm = labReportForm(panel, labs, entryId);

  return `${disclaimer}${labCategoryBar(labs, active)}${labReportDiscardHtml(
    panel,
    labs,
    entryId
  )}<div class="lab-rows">${rows}</div>${formError}${entryForm}${reportForm}`;
}

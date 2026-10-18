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
  PACE_INFO,
  escapeHtml,
  toNumber,
  clamp,
  fmtMl,
  relativeTime,
  ringHtml,
  categoryInfo,
  messageHtml,
  enabledTabs,
  areasForPerson,
} from "./health-o-mat-panel-base.js?v=0.8.0";

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
      : `<div class="tile-row muted">Lade\u2026</div>`;
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
    : "keine Messung";

  const wb = data.wellbeing || {};
  const wbState = wellbeingView(panel, data);
  const wbAt = wb.at ? relativeTime(wb.at) : "";

  const rest = goal > 0 ? Math.max(0, Math.round(goal - ml)) : null;
  const sub = goal > 0
    ? `Ziel ${fmtMl(goal)}${rest ? ` \u00B7 Rest ${fmtMl(rest)}` : ""}`
    : "Kein Tagesziel gesetzt";

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
    ? `<div class="tile-row"><span class="em" aria-hidden="true">${escapeHtml(wbState.emoji)}</span><span>${escapeHtml(wbState.label)}</span>${wbAt ? `<span class="muted">\u00B7 ${escapeHtml(wbAt)}</span>` : ""}</div>`
    : "";

  return `<button class="tile" data-action="open" data-entry="${escapeHtml(entryId)}" type="button">
      <div class="tile-head">
        <span class="dot"></span>
        <span class="tile-name">${escapeHtml(person.display_name)}</span>
        ${warn ? `<span class="status bad" title="Blutdruck oberhalb der Schwellen">\u26A0\uFE0F</span>` : ""}
      </div>
      ${drinkSection}
      ${bpRow}
      ${wbRow}
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
      : messageHtml("Lade Daten\u2026", false);
    return `${head}${tabBar}${inner}`;
  }

  const alert = panel._actionError
    ? `<div class="banner" role="alert">\u26A0\uFE0F ${escapeHtml(panel._actionError)}</div>`
    : "";

  let content;
  if (activeTab === "bp") content = bpTab(panel, data, entryId);
  else if (activeTab === "wellbeing") content = wellbeingTab(panel, data, entryId);
  else if (activeTab === "drink") content = drinkTab(panel, data, entryId);
  else content = messageHtml("Für diese Person ist kein Bereich aktiv.", false);

  return `${head}${tabBar}<div class="views">${alert}${content}</div>`;
}

function tabButton(activeTab, tab) {
  const active = activeTab === tab.key ? " active" : "";
  return `<button class="tab${active}" data-action="tab" data-tab="${tab.key}" type="button" role="tab" aria-selected="${active ? "true" : "false"}">${escapeHtml(tab.label)}</button>`;
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
      <div class="kv"><span class="k">Heute</span><span class="v">${fmtMl(ml)} / ${goalText} (${Math.round(percent)}%)</span></div>
      ${Number.isFinite(yesterday) ? `<div class="kv"><span class="k">Gestern</span><span class="v">${fmtMl(yesterday)}</span></div>` : ""}
      ${Number.isFinite(count) ? `<div class="kv"><span class="k">Buchungen</span><span class="v">${Math.round(count)}</span></div>` : ""}
      ${paceInfo ? `<div><span class="status ${paceInfo.cls}">${escapeHtml(paceInfo.text)}</span></div>` : ""}
    </div>`;

  const quick = QUICK_DRINKS.map(
    (d) => `<button class="btn" data-action="book" data-ml="${d.ml}" data-drink="${escapeHtml(d.type)}" type="button"${panel._busy ? " disabled" : ""}>
        <span>${escapeHtml(d.emoji)} ${escapeHtml(d.label)}</span>
        <span class="ml">${Math.round(d.ml)} ml</span>
      </button>`
  ).join("");

  const formError = panel._formError
    ? `<div class="msg error">${escapeHtml(panel._formError)}</div>`
    : "";

  const undo = `<button class="btn ghost" data-action="undo" type="button"${panel._busy ? " disabled" : ""}>\u21A9 Undo</button>`;

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
        <button class="btn" type="submit"${panel._busy ? " disabled" : ""}>Buchen</button>
      </form>
      ${formError}
      ${undo}
    </div>
    ${breakdown(panel, data)}`;
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
      <div class="muted">Heute nach Getränk</div>
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

  const formError = panel._formError
    ? `<div class="msg error">${escapeHtml(panel._formError)}</div>`
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
      <button class="btn" type="submit"${panel._busy ? " disabled" : ""}>\u{1F4BE} Speichern</button>
      ${formError}
    </form>`;

  return `<div class="card">${head}${avgHtml}</div>${warnHtml}${form}${bpTrend(bp)}`;
}

function bpTrend(bp) {
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

/* ---- Tab: Wohlbefinden (4.4) --------------------------------------------- */

export function wellbeingView(panel, data) {
  const wb = (data && data.wellbeing) || {};
  const live = panel._liveValue(data, "wellbeing", undefined);
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

function wellbeingTab(panel, data, entryId) {
  const view = wellbeingView(panel, data);
  const buttons = WELLBEING_STATES.map(
    (s) => `<button class="wb-btn${s.key === view.key ? " active" : ""}" data-action="wb" data-key="${s.key}" type="button"${panel._busy ? " disabled" : ""}>
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

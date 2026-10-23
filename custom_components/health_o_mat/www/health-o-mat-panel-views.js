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
  wellbeingScore,
  wellbeingChartHtml,
  wellbeingScale,
  wellbeingVisual,
  bpHistoryChartHtml,
} from "./health-o-mat-panel-base.js?v=0.11.0";

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
    ? `<div class="tile-row">${wellbeingVisual(wbState)}<span>${escapeHtml(wbState.label)}</span>${wbAt ? `<span class="muted">\u00B7 ${escapeHtml(wbAt)}</span>` : ""}</div>`
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

  return `<div class="card">${head}${avgHtml}</div>${warnHtml}${form}${bpHistoryChartHtml(bp.entries, { title: "Verlauf systolisch/diastolisch" })}`;
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
  return {
    key,
    emoji: liveEmoji || wb.emoji || (known && known.emoji) || "\u{1F642}",
    image: liveImage || wb.image || (known && known.image) || "",
    label: liveLabel || wb.label || (known && known.label) || "Keine Angabe",
    at: wb.at || (typeof live === "string" && live !== "unknown" ? live : ""),
    // Numerischer Score (1…N); null ohne Meldung (REQ-HOM-112).
    score,
  };
}

function wellbeingTab(panel, data, entryId) {
  const view = wellbeingView(panel, data);
  const scale = wellbeingScale(data);
  const scoreMax = scale.length || WELLBEING_SCORE_MAX;
  const buttons = scale.map(
    (s) => `<button class="wb-btn${s.key === view.key ? " active" : ""}" data-action="wb" data-key="${s.key}" type="button"${panel._busy ? " disabled" : ""}>
        ${wellbeingVisual(s)}
        <span class="lbl">${escapeHtml(s.label)}</span>
      </button>`
  ).join("");

  const at = view.at ? relativeTime(view.at) : "";
  const scoreText =
    view.score != null ? ` \u00B7 ${view.score} / ${scoreMax}` : "";
  const last = `<div class="tile-row">
      ${wellbeingVisual(view)}
      <span>Zuletzt: <strong>${escapeHtml(view.label)}</strong>${scoreText}</span>
      ${at ? `<span class="muted">\u00B7 ${escapeHtml(at)}</span>` : ""}
    </div>`;

  const scoreFormError = panel._formError
    ? `<div class="msg error">${escapeHtml(panel._formError)}</div>`
    : "";
  const scoreForm = `<form class="card" data-form="wellbeing">
      <div class="muted">Alternativ als Zahl (1\u2013${scoreMax})</div>
      <div class="bp-inputs">
        <label class="field">Wert
          <input type="number" inputmode="numeric" data-field="wb-score" min="1" max="${scoreMax}" step="1" placeholder="1\u2013${scoreMax}" />
        </label>
        <button class="btn" type="submit"${panel._busy ? " disabled" : ""}>\u{1F4BE} Melden</button>
      </div>
      ${scoreFormError}
    </form>`;

  /* Verlaufsliste UNTER dem Chart: pro Eintrag Zeitpunkt (relativ), Emoji,
   * Label und Score ("3 / 5"). Reine Anzeige aus `wellbeing.history` (letzte
   * 20) — kein rohes JSON, alle Texte escaped. Neueste Meldung OBEN
   * (`slice(-20).reverse()`), der Chart bleibt unveraendert chronologisch.
   * Unbekannte Keys/Felder fallen defensiv auf die kanonische Skala bzw.
   * einen neutralen Text zurueck. */
  const history = Array.isArray(data.wellbeing && data.wellbeing.history)
    ? data.wellbeing.history
    : [];
  const histItems = history
    .slice(-20)
    .reverse()
    .map((entry) => {
      if (!entry || typeof entry !== "object") return "";
      const entryKey = String(entry.key || "").toLowerCase();
      const knownState = scale.find((state) => state.key === entryKey);
      const entryAt = entry.ts ? relativeTime(entry.ts) : "";
      const entryLabel = entry.label || (knownState && knownState.label) || "Keine Angabe";
      const entryVisual = {
        emoji: entry.emoji || (knownState && knownState.emoji) || "\u{1F642}",
        image: entry.image || (knownState && knownState.image) || "",
      };
      const entryScore = wellbeingScore(entry);
      return `<li class="wb-hist">
          ${wellbeingVisual(entryVisual)}
          <span class="wb-hist-label">${escapeHtml(entryLabel)}</span>
          <span class="wb-hist-time">${escapeHtml(entryAt || "ohne Zeitangabe")}</span>
          ${entryScore != null ? `<span class="wb-hist-score">${entryScore} / ${scoreMax}</span>` : ""}
        </li>`;
    })
    .join("");
  const histHtml = histItems
    ? `<div class="card">
        <div class="muted">Verlauf</div>
        <ul class="wb-history">${histItems}</ul>
      </div>`
    : "";

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
    title: "Score-Verlauf",
  });

  return `<div class="card">
      <div class="muted">Wie geht es dir?</div>
      <div class="wb-row">${buttons}</div>
      ${last}
    </div>${scoreForm}${chartHtml}${histHtml}`;
}

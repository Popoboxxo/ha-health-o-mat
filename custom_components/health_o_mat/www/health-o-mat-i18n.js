/**
 * Health-O-Mat — UI translation loader (HA-native, no i18n framework).
 *
 * The panel is split into native ES modules without a bundler. This module is
 * the single place that talks to Home Assistant's translation WebSocket
 * command and keeps the per-language resource cache. It is deliberately
 * import-free so the unit tests can load it directly in Node (the sibling
 * modules import it with a cache-buster query instead).
 *
 * Contract:
 *   loadUiTranslations(hass)  -> "de" | "en" | …   (never throws)
 *   t(key, fallback, vars?)   -> translated string, `{placeholder}` interpolated
 *   currentLanguage()         -> language of the last load (default "de")
 *
 * Resources come from `frontend/get_translations` (category `common`,
 * integration `health_o_mat`) as a flat map:
 *
 *   {"component.health_o_mat.common.ui_panel_drink_today": "Heute", …}
 *
 * A failed load leaves an EMPTY cache for that language — the German fallback
 * text embedded in the renderers then stays visible. `t()` never renders a raw
 * `ui_…` key: a missing translation falls back to the caller's fallback (or ""
 * when there is none).
 */

const KEY_PREFIX = "component.health_o_mat.common.";
const DEFAULT_LANGUAGE = "de";
const WS_GET_TRANSLATIONS = "frontend/get_translations";
const INTEGRATION = "health_o_mat";

/** language -> { shortKey: translatedText } (present = load attempted). */
const _cache = new Map();
/** language -> Promise<void> of an in-flight load. */
const _inflight = new Map();
let _language = DEFAULT_LANGUAGE;

export function currentLanguage() {
  return _language;
}

export function normaliseLanguage(value) {
  const raw = value == null ? "" : String(value).trim().toLowerCase();
  if (!raw) return DEFAULT_LANGUAGE;
  // HA reports BCP-47 tags such as "de-DE"; the translation files use "de".
  return raw.split(/[-_]/)[0] || DEFAULT_LANGUAGE;
}

/** True if a load was already attempted for this language (success or not). */
export function hasUiTranslations(language) {
  return _cache.has(normaliseLanguage(language == null ? _language : language));
}

/** Test/reset hook — clears every cached language. */
export function resetUiTranslations() {
  _cache.clear();
  _inflight.clear();
  _language = DEFAULT_LANGUAGE;
}

/** Flat HA resource map -> short-key dictionary (prefix stripped). */
function normaliseResources(resources) {
  const out = Object.create(null);
  if (!resources || typeof resources !== "object") return out;
  Object.keys(resources).forEach((fullKey) => {
    const value = resources[fullKey];
    if (typeof value !== "string" || value === "") return;
    const key = fullKey.startsWith(KEY_PREFIX) ? fullKey.slice(KEY_PREFIX.length) : fullKey;
    out[key] = value;
  });
  return out;
}

/** `{name}` placeholders; unknown placeholders stay literal. */
export function interpolateUi(template, vars) {
  let out = template == null ? "" : String(template);
  if (vars && typeof vars === "object") {
    out = out.replace(/\{([A-Za-z0-9_]+)\}/g, (match, name) =>
      Object.prototype.hasOwnProperty.call(vars, name) && vars[name] != null
        ? String(vars[name])
        : match
    );
  }
  return out;
}

/**
 * Load (once per language) the integration's `common` translations.
 *
 * Returns the language that is active afterwards — never rejects. A missing
 * `hass`/`callWS` or a WS error simply stores an empty dictionary.
 */
export async function loadUiTranslations(hass) {
  const language = normaliseLanguage(hass && hass.language);
  _language = language;
  if (_cache.has(language)) return language;

  const running = _inflight.get(language);
  if (running) {
    await running;
    return _language;
  }

  const load = (async () => {
    let resources = null;
    try {
      if (hass && typeof hass.callWS === "function") {
        const result = await hass.callWS({
          type: WS_GET_TRANSLATIONS,
          language,
          category: "common",
          integration: [INTEGRATION],
        });
        resources = result && result.resources;
      }
    } catch (_error) {
      // Resilience: keep the German fallback texts, never break the UI.
      resources = null;
    }
    _cache.set(language, normaliseResources(resources));
  })();

  _inflight.set(language, load);
  try {
    await load;
  } finally {
    _inflight.delete(language);
  }
  return _language;
}

/**
 * Translate a flat `common` key.
 *
 * @param {string} key      short key (`ui_panel_…`) or full resource key
 * @param {string} fallback German text used when the key is not translated
 * @param {object} [vars]   values for `{placeholder}` interpolation
 */
export function t(key, fallback, vars) {
  const rawKey = key == null ? "" : String(key);
  const shortKey = rawKey.startsWith(KEY_PREFIX) ? rawKey.slice(KEY_PREFIX.length) : rawKey;
  const dict = _cache.get(_language);
  const value = dict && typeof dict === "object" ? dict[shortKey] : "";
  if (typeof value === "string" && value !== "") return interpolateUi(value, vars);
  return interpolateUi(fallback == null ? "" : fallback, vars);
}

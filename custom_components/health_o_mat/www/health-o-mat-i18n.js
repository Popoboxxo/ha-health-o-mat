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
 *   loadUiTranslations(hass)        -> "de" | "en" | …   (never throws)
 *   t(key, fallback, vars?)         -> translated string, `{placeholder}` interpolated
 *   loadExceptionTranslations(hass) -> "de" | "en" | …   (never throws)
 *   tError(err)                     -> localized error text (never empty)
 *   currentLanguage()               -> language of the last load (default "de")
 *
 * Resources come from `frontend/get_translations` (integration `health_o_mat`)
 * as flat maps in two categories:
 *
 *   common:      {"component.health_o_mat.common.ui_panel_drink_today": "Heute", …}
 *   exceptions:  {"component.health_o_mat.exceptions.amount_out_of_range.message": "…"}
 *
 * A failed load leaves an EMPTY cache for that language — the German fallback
 * text embedded in the renderers then stays visible. `t()` never renders a raw
 * `ui_…` key: a missing translation falls back to the caller's fallback (or ""
 * when there is none). `tError()` never renders a raw `ui_…` key either: an
 * unknown code falls back to the neutral server `message`, then to the code.
 */

const KEY_PREFIX = "component.health_o_mat.common.";
const ERROR_KEY_PREFIX = "component.health_o_mat.exceptions.";
const DEFAULT_LANGUAGE = "de";
const WS_GET_TRANSLATIONS = "frontend/get_translations";
const INTEGRATION = "health_o_mat";

/** language -> { shortKey: translatedText } (present = load attempted). */
const _cache = new Map();
/** language -> Promise<void> of an in-flight load. */
const _inflight = new Map();
/** language -> { "<code>.message": translatedText } (exceptions catalog). */
const _errorCache = new Map();
/** language -> Promise<void> of an in-flight exceptions load. */
const _errorInflight = new Map();
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

/** True if the `exceptions` catalog was already attempted for this language. */
export function hasErrorTranslations(language) {
  return _errorCache.has(normaliseLanguage(language == null ? _language : language));
}

/** Test/reset hook — clears every cached language (both categories). */
export function resetUiTranslations() {
  _cache.clear();
  _inflight.clear();
  _errorCache.clear();
  _errorInflight.clear();
  _language = DEFAULT_LANGUAGE;
}

/** Flat HA resource map -> short-key dictionary (prefix stripped). */
function normaliseResources(resources, prefix) {
  const out = Object.create(null);
  if (!resources || typeof resources !== "object") return out;
  Object.keys(resources).forEach((fullKey) => {
    const value = resources[fullKey];
    if (typeof value !== "string" || value === "") return;
    const key = fullKey.startsWith(prefix) ? fullKey.slice(prefix.length) : fullKey;
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
 * Fetch one translation category — never rejects.
 *
 * @returns {Promise<object|null>} flat resource map or null on failure
 */
async function fetchResources(hass, language, category) {
  try {
    if (hass && typeof hass.callWS === "function") {
      const result = await hass.callWS({
        type: WS_GET_TRANSLATIONS,
        language,
        category,
        integration: [INTEGRATION],
      });
      return result && result.resources ? result.resources : null;
    }
  } catch (_error) {
    // Resilience: keep the fallback texts, never break the UI.
  }
  return null;
}

/**
 * Load (once per language) the integration's `exceptions` translations.
 *
 * Returns the language that is active afterwards — never rejects.
 */
export async function loadExceptionTranslations(hass) {
  const language = normaliseLanguage(hass && hass.language);
  _language = language;
  if (_errorCache.has(language)) return language;

  const running = _errorInflight.get(language);
  if (running) {
    await running;
    return _language;
  }

  const load = (async () => {
    const resources = await fetchResources(hass, language, "exceptions");
    _errorCache.set(language, normaliseResources(resources, ERROR_KEY_PREFIX));
  })();

  _errorInflight.set(language, load);
  try {
    await load;
  } finally {
    _errorInflight.delete(language);
  }
  return _language;
}

/**
 * Load (once per language) the integration's `common` translations.
 *
 * The `exceptions` catalog is loaded in parallel (both caches are per
 * language), so callers only need this one entry point.
 *
 * Returns the language that is active afterwards — never rejects.
 */
export async function loadUiTranslations(hass) {
  const language = normaliseLanguage(hass && hass.language);
  _language = language;
  if (_cache.has(language)) {
    if (!_errorCache.has(language)) await loadExceptionTranslations(hass);
    return language;
  }

  const running = _inflight.get(language);
  if (running) {
    await running;
    return _language;
  }

  const load = (async () => {
    const [resources] = await Promise.all([
      fetchResources(hass, language, "common"),
      loadExceptionTranslations(hass),
    ]);
    _cache.set(language, normaliseResources(resources, KEY_PREFIX));
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

/**
 * Translate a structured error object (`{translation_key, translation_placeholders}`
 * or the batch `{code, params}`).
 *
 * Priority: the HA `exceptions` catalog text (interpolated) → the neutral server
 * `message` → the code. Never an empty string, never a raw `ui_…` key.
 *
 * @param {object|string} err error object or plain message
 */
export function tError(err) {
  if (err == null) return "";
  if (typeof err !== "object") return String(err);

  const key = err.translation_key || err.code || "";
  const vars = err.translation_placeholders || err.params || {};
  const dict = key ? _errorCache.get(_language) : null;
  const text = dict && typeof dict === "object" ? dict[`${key}.message`] : "";
  if (typeof text === "string" && text !== "") return interpolateUi(text, vars);
  if (err.message != null && String(err.message) !== "") return String(err.message);
  if (key) return String(key);
  return "";
}

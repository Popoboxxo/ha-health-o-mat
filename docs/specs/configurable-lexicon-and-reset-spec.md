# Spec: Configurable Drink Lexicon & Configurable Daily-Reset Hour

Status: draft (concept only, no implementation yet)
Branch: `feat/configurable-lexicon-and-reset`
Author input: user-supplied Ist-Analyse + design proposal (verified against current
code on this branch, see "Deviations" for every point where reality required a
different call).

---

## Feature 1 — Configurable drink lexicon

### Problem

`DRINK_LEXICON` in `const.py` (~19 entries, `dict[str, tuple[str, int]]`) is a
hardcoded module constant. It is read by exactly one call site today:
`parser.parse()` (verified via `grep -rn "parse(" custom_components/health_o_mat`
— the only other candidate, the `add_drink` service in `__init__.py`, takes
`amount_ml`/`drink_type` directly and never calls `parser.parse()`, so it is out
of scope). Users cannot add/rename/remove words without editing the integration
source.

### Affected files

| File | Change |
|---|---|
| `custom_components/health_o_mat/parser.py` | add `format_lexicon()`, `parse_lexicon_text()`; extend `parse()` with optional `lexicon` param |
| `custom_components/health_o_mat/const.py` | no change (constant stays as the built-in default) |
| `custom_components/health_o_mat/text.py` | read `entry.options["drink_lexicon"]`, pass to `parser.parse()` |
| `custom_components/health_o_mat/config_flow.py` | new options step `drink_lexicon` after `quick_drinks`, before entry creation |
| `custom_components/health_o_mat/strings.json` | new `options.step.drink_lexicon` + `options.error.invalid_lexicon_format` |
| `custom_components/health_o_mat/translations/de.json` | mirror of the above, German |
| `custom_components/health_o_mat/translations/en.json` | mirror of the above, English |
| `tests/conftest.py` | add fake `homeassistant.helpers.selector` module (new import, not covered by the current fake-module list) |
| `tests/test_parser.py` | new cases for `format_lexicon`/`parse_lexicon_text` (see Acceptance Criteria) |

`__init__.py`, `sensor.py`, `binary_sensor.py`, `services.yaml` — **not touched**
for this feature (no other consumer of the lexicon exists).

### Interface contracts

```python
# parser.py
def format_lexicon(lexicon: dict[str, tuple[str, int]]) -> str:
    """Serialize a lexicon dict to the editable 'word=Type,ml' text format,
    one entry per line, in dict iteration order."""

def parse_lexicon_text(text: str) -> dict[str, tuple[str, int]]:
    """Parse the multiline 'word=Type,ml' format into a lexicon dict.

    Blank lines and lines starting with '#' are ignored.
    Raises ValueError (1-indexed line number + offending line) on the first
    malformed line: missing '=' or ',', empty word/type, ml not an int,
    ml <= 0 or ml > const.MAX_AMOUNT_ML.
    Word is lower-cased + stripped (must match parser._normalize() output);
    Type is stripped but keeps its casing (canonical display form, e.g. "Kaffee").
    """

def parse(text: str, lexicon: dict[str, tuple[str, int]] = DRINK_LEXICON) -> DrinkParse:
    """Unchanged behavior when called without `lexicon` (existing tests keep
    passing). Callers with a per-entry lexicon pass it explicitly."""
```

`parse_lexicon_text`/`format_lexicon` stay HA-free (only `re`, `const.MAX_AMOUNT_ML`)
— importable and unit-testable the same way as the existing parser tests.

```python
# config_flow.py — new step
async def async_step_drink_lexicon(self, user_input=None):
    ...
```

Options schema key: `drink_lexicon` → `entry.options["drink_lexicon"]`, stored as
`dict[str, tuple[str, int]]`.

**Persistence nuance (must be documented, not "fixed"):** `ConfigEntry.options`
round-trips through HA's JSON storage. A `tuple` written into `options` comes
back as a `list` after a restart/reload. `parse()`'s tuple-unpacking
(`canonical, default_ml = lexicon[key]`) works identically for a 2-element list,
so this is safe — but no code may do `isinstance(value, tuple)` on a lexicon
entry read from `entry.options`.

### Data flow

1. **Read (first form open):** `async_step_drink_lexicon` reads
   `self.config_entry.options.get("drink_lexicon")`. If present (dict), format
   it back to text via `format_lexicon()`. If absent (fresh entry), format
   `const.DRINK_LEXICON` (the built-in default) the same way. This text is the
   form's `default=`.
2. **Write (form submit):** raw textarea value → `parser.parse_lexicon_text()`.
   On success, the resulting dict is stored into `self._pending["drink_lexicon"]`
   and persisted via the existing terminal `self.async_create_entry(title="", data=self._pending)`
   (same commit point already used for `daily_goal_ml`/`quick_drinks`).
   On failure, re-show the same step with `errors["base"] = "invalid_lexicon_format"`
   and the user's original (unparsed) text preserved as the field default — same
   pattern as `async_step_user`'s error handling for `person`.
3. **Consume (runtime):** `text.FreeTextDrinkEntity.async_set_value()` reads
   `self._entry.options.get("drink_lexicon") or DRINK_LEXICON` **on every call**
   (on-read, no cached/mirrored copy in `runtime_data` — there is exactly one
   call site, so a `HealthOMatData` mirror would be an unrequested abstraction).
   This means an options change takes effect immediately, no reload/listener
   needed for this feature (unlike `daily_goal_ml`, which is mirrored into
   `runtime_data` because multiple sensors read it every update cycle).

No merge with defaults at any point — the stored dict is always the complete,
authoritative lexicon (WYSIWYG, as specified).

### Error handling

| Case | Result |
|---|---|
| Line without `=` or without `,` | `ValueError("Line N: expected 'word=Type,ml', got '<line>'")` → `errors["base"] = "invalid_lexicon_format"`, `description_placeholders={"detail": str(err)}` |
| Empty word or empty type | `ValueError("Line N: word and type must not be empty")` |
| `ml` not parseable as `int` | `ValueError("Line N: ml must be a whole number")` |
| `ml <= 0` or `ml > MAX_AMOUNT_ML` | `ValueError("Line N: ml must be between 1 and {MAX_AMOUNT_ML}")` |
| Blank line / line starting with `#` | ignored, not an error |
| Duplicate word across lines | last occurrence wins (plain dict-assignment semantics) — **not** treated as an error; no dedup UI planned (YAGNI) |

### Translation diff plan

`strings.json` (master, English) — add to `options.step`:
```json
"drink_lexicon": {
  "title": "Drink dictionary",
  "description": "One entry per line: word=Type,ml (e.g. kaffee=Coffee,250). Lines starting with '#' are comments.",
  "data": { "drink_lexicon": "Drink dictionary" }
}
```
and to `options.error`:
```json
"invalid_lexicon_format": "Invalid entry: {detail}"
```
Mirror both blocks verbatim into `translations/en.json`, and translated
(German UI text, format token `word=Type,ml` stays literal/untranslated since
it is a fixed syntax) into `translations/de.json`, following the exact
structural pattern already used for `quick_drinks` (see current `strings.json`
`options.step.quick_drinks`).

### Acceptance criteria (testable)

1. `parser.format_lexicon(DRINK_LEXICON)` round-trips: `parser.parse_lexicon_text(parser.format_lexicon(DRINK_LEXICON)) == DRINK_LEXICON`.
2. `parser.parse_lexicon_text("kaffee=Kaffee,250")` → `{"kaffee": ("Kaffee", 250)}`.
3. `parser.parse_lexicon_text("# comment\n\nkaffee=Kaffee,250")` → same as above (comments/blank lines ignored).
4. `parser.parse_lexicon_text("kaffee=Kaffee")` (missing `,ml`) raises `ValueError`.
5. `parser.parse_lexicon_text("kaffee=Kaffee,abc")` (ml not int) raises `ValueError`.
6. `parser.parse_lexicon_text("kaffee=Kaffee,0")` and `...,20000` (out of `1..MAX_AMOUNT_ML`) raise `ValueError`.
7. `parser.parse("kaffee", lexicon={"kaffee": ("Espresso", 40)}).drink_type == "Espresso"` — custom lexicon overrides default resolution.
8. `parser.parse("kaffee 300ml")` (no `lexicon` arg) behaves exactly as before (regression guard for existing `tests/test_parser.py`).
9. Config flow: submitting `drink_lexicon` step with valid text creates the entry with `options["drink_lexicon"]` equal to the parsed dict.
10. Config flow: submitting malformed text re-shows the `drink_lexicon` step with `errors == {"base": "invalid_lexicon_format"}` and does not advance/create the entry.
11. `text.FreeTextDrinkEntity.async_set_value()` with a custom `entry.options["drink_lexicon"]` resolves a word only present in that custom dict (not in `const.DRINK_LEXICON`).

---

## Feature 2 — Configurable daily-reset hour

### Problem

`logic.day_start()`/`logic.today_sums()` already accept `hour`/`minute` and are
on-read/DST-safe (no reset job) — the underlying mechanism is done. Every
caller currently omits `hour`, hardcoding midnight. Confirmed call sites via
`grep -rn "today_sums(\|yesterday_window("`:

- `sensor.py:44` — `HealthOMatSensor._today_sums()`
- `sensor.py:67` — `TodaySensor.extra_state_attributes()` → `logic.yesterday_window(now)`
- `binary_sensor.py:34` — `HealthOMatBinary._today_ml()`

(`logic.yesterday_window` is an additional call site beyond the two explicitly
named in the task — see "Deviations" for why it must be included.)

### Affected files

| File | Change |
|---|---|
| `custom_components/health_o_mat/config_flow.py` | add `daily_reset_hour` field to existing `init` options step |
| `custom_components/health_o_mat/sensor.py` | pass `hour=` in `_today_sums()` and in the `yesterday_window()` call |
| `custom_components/health_o_mat/binary_sensor.py` | pass `hour=` in `_today_ml()` |
| `custom_components/health_o_mat/strings.json` | new `options.step.init.data.daily_reset_hour` |
| `custom_components/health_o_mat/translations/de.json` | mirror, German |
| `custom_components/health_o_mat/translations/en.json` | mirror, English |
| `logic.py` | **no change** — `hour`/`minute` params already exist |
| `__init__.py` | **no change** — `daily_reset_hour` is read on-read from `entry.options` at render time in sensor/binary_sensor, not mirrored into `HealthOMatData`/`runtime_data` (see rationale below) |

### Interface contracts

Options schema key: `daily_reset_hour: int`, `vol.All(vol.Coerce(int), vol.Range(min=0, max=23))`, default `0`.

```python
# config_flow.py, async_step_init — add alongside daily_goal_ml
vol.Optional(
    "daily_reset_hour",
    default=self.config_entry.options.get("daily_reset_hour", 0),
): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
```

No new function signatures needed in `logic.py`. Call-site change only:

```python
# sensor.py — HealthOMatSensor._today_sums
def _today_sums(self) -> dict:
    hour = self._entry.options.get("daily_reset_hour", 0)
    return logic.today_sums(self._data.get("drinks", []), dt_util.now(), hour=hour)

# sensor.py — TodaySensor.extra_state_attributes
hour = self._entry.options.get("daily_reset_hour", 0)
y_start, y_end = logic.yesterday_window(now, hour=hour)

# binary_sensor.py — HealthOMatBinary._today_ml
def _today_ml(self) -> int:
    hour = self._entry.options.get("daily_reset_hour", 0)
    return logic.today_sums(self._data.get("drinks", []), dt_util.now(), hour=hour)["total_ml"]
```

### Data flow

`entry.options["daily_reset_hour"]` is read **on every property access** directly
from `self._entry.options` in `sensor.py`/`binary_sensor.py` — the same
`self._entry` reference already used for `self._entry.runtime_data.daily_goal_ml`
(entity's stored `_entry`, confirmed live in `entity.py`/`sensor.py`/`binary_sensor.py`).

**No `runtime_data` mirror, no `_options_updated` listener changes.** Rationale:
`_apply_options`/`_options_updated` mirror `daily_goal_ml` into `runtime_data`
because that value is read many times per update across multiple sensors and the
mirror was an existing, already-established pattern for *cheap repeated reads of
a rarely-changing value where the source of truth is `entry.options`*. Reading
`entry.options` directly for `daily_reset_hour` is exactly as cheap (dict `.get()`,
no I/O) as reading `runtime_data.daily_goal_ml` — adding a second mirror field,
a second sync point in `_apply_options`/`_options_updated`, just to save one
dict lookup, is the unrequested-abstraction rung on the ladder. Options changes
take effect on the next entity read with zero extra plumbing (same as
`entry.options.get("quick_drinks")`, which button.py already reads directly
without a `runtime_data` mirror — verified consistent existing pattern).

### Error handling

`vol.Range(min=0, max=23)` + `vol.Coerce(int)` reject out-of-range/non-numeric
input at the form-validation layer (framework-level `vol.Invalid`, same as the
existing `daily_goal_ml` field) — no custom validator needed.

### Translation diff plan

`strings.json` `options.step.init.data` — add:
```json
"daily_reset_hour": "Daily reset hour (0-23)"
```
Mirror into `translations/en.json` identically, and into `translations/de.json`
as e.g. `"Reset-Uhrzeit des Tageszählers (0-23)"`. No new step, no new title —
existing `init` step title/description are reused.

### Acceptance criteria (testable)

1. `logic.today_sums(drinks, now, hour=6)` (already covered by existing `logic.py` design, but add a regression test if `tests/test_logic.py` doesn't already parametrize `hour`) — a drink booked at 05:00 counts toward the *previous* tracking day when `hour=6`.
2. Config flow `init` step schema contains a `daily_reset_hour` field with `vol.Range(min=0, max=23)`; submitting `24` or `-1` is rejected by voluptuous before reaching `_pending`.
3. `TodaySensor.native_value` / `HealthOMatSensor._today_sums()` reflects `entry.options["daily_reset_hour"]` immediately after an options update (no reload required) — mock `entry.options = {"daily_reset_hour": 6}` and assert `logic.today_sums` was called with `hour=6`.
4. `GoalReachedEntity.is_on` (via `HealthOMatBinary._today_ml`) uses the same `hour` value as `TodaySensor` for the same entry (consistency between sensor and binary_sensor for one config).
5. `TodaySensor.extra_state_attributes()["yesterday_ml"]` window is anchored to the same `daily_reset_hour` as `native_value`'s "today" window (regression guard for the yesterday_window call site — see Deviations).
6. Default (`daily_reset_hour` absent from `entry.options`, e.g. entries created before this feature) behaves exactly as today: midnight reset, no behavior change for existing users.

---

## Deviations from proposed design

1. **`yesterday_window()` call site added to Feature 2 scope.** The task named
   only `today_sums(` as the grep target for callers-to-update. Tracing
   `sensor.py`'s `TodaySensor.extra_state_attributes()` end-to-end shows it also
   calls `logic.yesterday_window(now)` (no `hour`) to compute the `yesterday_ml`
   attribute. Leaving this uncorrected would desynchronize "today" and
   "yesterday" windows the moment `daily_reset_hour != 0` (e.g. a drink at 02:00
   with reset hour 6 would be double-counted as "yesterday" by one window and
   "today" by the other, or vice versa) — a root-cause fix must cover every
   caller that derives a day boundary from the same options value, not just the
   two literally named. Included in scope; flagged here for visibility since it
   widens the diff beyond the literal instruction.

2. **`vol.Invalid` requested, manual `errors` dict used instead (Feature 1).**
   The task says "Parse-Fehler -> vol.Invalid mit klarer Meldung". The existing
   codebase convention for Config-/Options-Flow validation errors (see
   `async_step_user`'s handling of the `person` field) is a manually built
   `errors: dict[str, str]` passed to `async_show_form`, not an exception raised
   from inside a `vol.Schema` validator. Both mechanisms ultimately produce the
   same translated user-facing error text; using the established local pattern
   avoids introducing a second, inconsistent error-signaling style in the same
   file. `parse_lexicon_text()` raises a plain `ValueError` (kept HA-free, no
   `voluptuous` import needed in `parser.py`), which `config_flow.py` catches
   and translates into the `errors["base"]` convention already used in this file.

3. **No `runtime_data` mirror for `daily_reset_hour`.** See "Data flow" in
   Feature 2 above — reading `entry.options` directly is the established
   pattern for infrequently-changing options with a single or few readers
   (`quick_drinks` in `button.py`); `runtime_data` mirroring is reserved for
   values read on every coordinator tick across multiple entities where the
   existing code already does it (`daily_goal_ml`). Adding a mirror here would
   duplicate `_apply_options`/`_options_updated` logic for no measurable benefit.

4. **Lexicon text-field error detail stays in English inside a translated
   sentence.** `parse_lexicon_text()`'s `ValueError` message (line number +
   offending raw line) is technical/positional, not prose — translating "Line
   N: expected 'word=Type,ml', got '...'" per-locale would require either a
   structured exception type (over-engineering for one error path) or
   hardcoding the format string twice (DE/EN) with no behavioral difference.
   The translated wrapper sentence (`options.error.invalid_lexicon_format`,
   `"Invalid entry: {detail}"`) is localized; only the embedded technical detail
   stays literal. Accepted as a minor, known UX limitation — not a functional
   gap.

5. **No dedup/merge UI for lexicon entries.** Per constraint (no merge
   mechanism), duplicate words in the pasted text simply resolve via last-line-wins
   dict-assignment order. No warning, no separate error class — YAGNI.

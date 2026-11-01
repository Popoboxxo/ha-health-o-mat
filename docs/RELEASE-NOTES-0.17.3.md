> ✅ **Handlungshinweis — nichts zu tun außer Update.** 0.17.3 ist rein additiv:
> keine `unique_id`-Änderung, keine Entity-ID-Änderung, kein Store-Schema-Bump,
> keine neue `config entry`-Version. Ein normales Update über HACS genügt.

# v0.17.3 — Laborwerte im Verlauf sichtbar und korrigierbar

## Zusammenfassung

Feature-Release (MINOR): Laborwerte sind jetzt ein vollwertiges Verlaufsziel.
`health_o_mat/list_history` akzeptiert `kind=lab_values` (inkl. `include_voided`)
und liefert die stabilen Eintrags-IDs, mit denen sich ein Laborwert über
`void_entry`/`restore_entry` korrigieren und wiederherstellen lässt — symmetrisch
zu Getränken, Blutdruck und Wohlbefinden. Der Labor-Verlauf ist paginierbar
(`limit`/`offset`/`has_more`) und zeitlich filterbar (`since`), damit die mit jedem
Bericht wachsende Liste nicht komplett übertragen werden muss. Ein interner
Sonderweg für Laborwerte (`_LAB_STATE_*`) ist entfallen: die Ziel-Auflösung liegt
jetzt vollständig in einer Tabelle.

## ✨ New features

### Laborwerte als Verlaufsziel

`list_history` mit `kind=lab_values` (Aliase `lab_value`, `lab_readings`) liefert
je Eintrag `id`, `ts`, `created_at`, `voided_at`, `voided_by`, `void_reason` sowie
`marker_key`, `value`, `unit`, `reported_value` und `reported_unit` — neueste
zuerst. `include_voided=true` nimmt gelöschte Einträge samt Lösch-Metadaten mit.

### Pagination und Zeitfilter

- `limit` (1…1000): Laborwerte haben ohne Angabe einen Default von **200**; ein
  explizit zu großer Wert wird als `invalid_format` abgewiesen statt still gekappt.
- `offset` (Default 0) und `has_more` im Ergebnis bilden ein deterministisches
  Fenster.
- `since`: inklusive Untergrenze als ISO-Zeitpunkt, verglichen auf dem
  **UTC-Instant** — `…+02:00` und `…Z` für denselben Moment verhalten sich gleich
  (offset- und DST-fest).
- Die bisherigen Ziele (`drinks`, `blood_pressure`, `wellbeing`) bleiben ohne
  `limit` unverändert unbegrenzt — Bestands-Clients sehen keinen Unterschied.

### Korrigieren und Wiederherstellen für Laborwerte

`void_entry`/`restore_entry` und `void`/`restore` über WebSocket akzeptieren
`kind=lab_values`; die Zuordnung zu den Store-Methoden kommt aus einer Tabelle in
`logic.py` statt aus einem Sonderpfad in der Service-Schicht. Ein globales
„letzten Laborwert entfernen“ gibt es weiterhin nicht — das Undo bleibt
marker-spezifisch (`remove_last_lab_value`); `remove_last_entry` mit
`kind=lab_values` meldet das jetzt als Validierungsfehler statt als `KeyError`.

## 💥 Breaking changes

Keine. Rein additive Änderung: neue optionale Parameter, ein zusätzliches
Verlaufsziel und ein zusätzliches Feld (`has_more`) in der Antwort. Bestehende
Aufrufe von `list_history`, `void_entry` und `restore_entry` verhalten sich
unverändert.

- Keine `unique_id`-Änderung, keine Entity-ID-Änderung, kein Migrationsschritt
  (`async_migrate_entry` bleibt unverändert).
- `report_ref` bleibt privat: es wird nur mit `include_report_ref: true`
  mitgeliefert (Default `false`).

## Upgrade

1. Update über HACS installieren.
2. Home Assistant neu starten (Reload genügt für die Integration, ein Neustart ist
   unschädlich).
3. Keine weiteren Schritte. Es gibt nichts zu migrieren.

## Kompatibilität

- `manifest.version` 0.17.3, `config entry`-Version unverändert.
- Store-Schema unverändert; vorhandene Labor-, Getränke-, Blutdruck- und
  Wohlbefinden-Daten bleiben unberührt.
- Neu: `docs/PLAN-OPEN-ISSUES.md` — interner Umsetzungsplan für die offenen
  Issues (#28, #31, #33, #70–#73).

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.17.2...v0.17.3

---

> ✅ **Action required — nothing but the update.** 0.17.3 is purely additive: no
> `unique_id` change, no entity-id change, no store-schema bump, no new
> `config entry` version. A regular HACS update is enough.

# v0.17.3 — Lab values in the history, visible and correctable

## Summary

Feature release (MINOR): lab values are a first-class history target now.
`health_o_mat/list_history` accepts `kind=lab_values` (including `include_voided`)
and returns the stable entry ids needed to void or restore a lab value via
`void_entry`/`restore_entry` — symmetric to drinks, blood pressure and wellbeing.
The lab history is paginated (`limit`/`offset`/`has_more`) and time-filterable
(`since`), so the list that grows with every report no longer has to be transferred
in full. An internal special path for lab values (`_LAB_STATE_*`) is gone: target
resolution now lives entirely in a table.

## ✨ New features

### Lab values as a history target

`list_history` with `kind=lab_values` (aliases `lab_value`, `lab_readings`) returns
`id`, `ts`, `created_at`, `voided_at`, `voided_by`, `void_reason` plus
`marker_key`, `value`, `unit`, `reported_value` and `reported_unit` per entry —
newest first. `include_voided=true` includes voided entries with their void
metadata.

### Pagination and time filter

- `limit` (1…1000): lab values default to **200** when omitted; an explicitly too
  large value is rejected as `invalid_format` instead of being silently capped.
- `offset` (default 0) and `has_more` in the result form a deterministic window.
- `since`: an inclusive ISO lower bound compared on the **UTC instant** — `…+02:00`
  and `…Z` for the same moment behave identically (offset- and DST-proof).
- The existing kinds (`drinks`, `blood_pressure`, `wellbeing`) stay unbounded
  without `limit` — existing clients see no difference.

### Void and restore for lab values

`void_entry`/`restore_entry` and the WebSocket `void`/`restore` accept
`kind=lab_values`; the store-method mapping comes from a table in `logic.py`
instead of a special path in the service layer. There is still no global "remove
last lab value" — that undo stays marker-specific (`remove_last_lab_value`);
`remove_last_entry` with `kind=lab_values` now reports a validation error instead
of a `KeyError`.

## 💥 Breaking changes

None. Purely additive: new optional parameters, one additional history target and
one additional field (`has_more`) in the response. Existing `list_history`,
`void_entry` and `restore_entry` calls behave unchanged.

- No `unique_id` change, no entity-id change, no migration step
  (`async_migrate_entry` unchanged).
- `report_ref` stays private: it is only included with `include_report_ref: true`
  (default `false`).

## Upgrade

1. Install the update via HACS.
2. Restart Home Assistant (a reload is enough for the integration; a restart is
   harmless).
3. Nothing else. There is nothing to migrate.

## Compatibility

- `manifest.version` 0.17.3, `config entry` version unchanged.
- Store schema unchanged; existing lab, drink, blood-pressure and wellbeing data is
  untouched.
- New: `docs/PLAN-OPEN-ISSUES.md` — internal implementation plan for the open
  issues (#28, #31, #33, #70–#73).

## Full changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.17.2...v0.17.3

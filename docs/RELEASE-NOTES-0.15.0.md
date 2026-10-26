# v0.15.0 — Wohlbefinden-Zahleneingabe

## Zusammenfassung

Minor-Release: ergänzt eine **Number-Entity für das Wohlbefinden**. Bislang
ließ sich der Zustand nur über das Dropdown (`select.…_wellbeing`) oder die
Melden-Buttons setzen; jetzt gibt es mit `number.…_wellbeing_input` ein
korrespondierendes Zahlen-Eingabefeld (1–10) — auch ohne UI direkt über die
Entity nutzbar.

## ✨ New features

- **`number.…_wellbeing_input`** — Wohlbefinden als Zahl **1–10**
  (1 = „Sehr schlecht" … 10 = „Ausgezeichnet"), `step: 1`, Modus `box`.
  Der Wert wird auf denselben Status-Key abgebildet wie beim Select und bei
  den Melden-Buttons und über denselben Store-Pfad gemeldet. Verlauf,
  `wellbeing_score` und Wellbeing-Chronologie bleiben dadurch konsistent.
- Die Entity folgt dem Bereichs-Schalter `wellbeing`: Ist Wohlbefinden für
  eine Person deaktiviert (`areas.wellbeing: false`), wird sie nicht erzeugt.
- Deutsche und englische Übersetzung („Wohlbefinden-Eingabe" /
  „Wellbeing input").

## 💥 Breaking changes

Keine. Es kommt ausschließlich eine **neue** Entity hinzu; bestehende
`unique_id`s, Entity-IDs, Store-Schema und Backup-Format bleiben unverändert.

## Migration

Update über HACS installieren und Home Assistant neu starten. Kein weiterer
Schritt erforderlich. Die neue Entity erscheint automatisch bei Personen mit
aktivem Wohlbefinden-Bereich.

## Vollständiger Changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.14.1...v0.15.0

---

# v0.15.0 — Wellbeing number input (English)

## Summary

Minor release: adds a **number entity for wellbeing**. Previously the state
could only be set via the dropdown (`select.…_wellbeing`) or the report
buttons; `number.…_wellbeing_input` now provides the matching numeric input
(1–10) that can also be used directly without the UI.

## ✨ New features

- **`number.…_wellbeing_input`** — wellbeing as a number **1–10**
  (1 = "Very bad" … 10 = "Excellent"), `step: 1`, `box` mode. The value maps
  to the same status key as the select and the report buttons and is reported
  through the same store path, so history, `wellbeing_score` and the wellbeing
  chronology stay consistent.
- The entity follows the `wellbeing` area toggle: if wellbeing is disabled for
  a person (`areas.wellbeing: false`), it is not created.
- German and English translations ("Wohlbefinden-Eingabe" / "Wellbeing input").

## 💥 Breaking changes

None. Only a **new** entity is added; existing `unique_id`s, entity IDs,
store schema and backup format are unchanged.

## Migration

Install the update via HACS and restart Home Assistant. No further steps are
required. The new entity appears automatically for persons with the wellbeing
area enabled.

## Full changelog

https://github.com/Popoboxxo/ha-health-o-mat/compare/v0.14.1...v0.15.0

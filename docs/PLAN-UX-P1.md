# Umsetzungsplan UX-P1 — Release 0.14.0

**Status:** Umgesetzt (Branch `feat/ux-p1`, 2026-10-26) · **Release:** `0.14.0` vorbereitet
**Scope:** P1-Punkte **1, 2, 4, 5, 6, 7** aus dem Usability-Check
**Nicht in Scope:** P1-Punkt 3 (Mehrbenutzer/Datenschutz/ACL) — siehe §12
**Release-Schnitt:** **ein** Release `0.14.0` (Entscheidung des Users)
**Verwandt:** `docs/IDEATION-VISION.md`, `docs/REQUIREMENTS.md`

## 0. Entscheidungen aus der Klärung

| Thema | Entscheidung |
|---|---|
| Visionspapier | `docs/IDEATION-VISION.md`, 2–3 Jahre, intern + Community |
| Plan | `docs/PLAN-UX-P1.md` (dieses Dokument) |
| Korrigierbarkeit | Verlauf + Löschen + Undo für Getränke, Blutdruck und Wohlbefinden; kein volles Editieren |
| Löschsemantik | **Audit-Log / unveränderlich** — Void/Restore statt Hard-Delete; **dauerhaft kein Hard-Delete in der UI** |
| Restore | Merge + Replace, **zusätzlich Teil-Restore** (Person/Datensatz/Zeitraum), Dry-Run |
| i18n | **Nur HA-nativ de/en** (kein eigenes i18n-Framework) |
| Reminder/Reports | Eingebaute Reminder + Wochenbericht + Blueprints |
| Reminder-Kanäle | beliebiger `notify.*`-Service, Fallback `persistent_notification` |
| Wochenbericht | **nur Notification** (Markdown), keine Datei |
| Karten-Verlauf | `show_history` Default **aus**; Panel zeigt den vollen Verlauf |
| Audit-Aufbewahrung | Default **Cap 1000 Ereignisse/Person**, im Admin **unbegrenzt** (`0`) einstellbar |
| Onboarding | Wizard mit optionalen Schritten und Defaults |
| Rückdatieren | Datum/Zeit **unbegrenzt** in die Vergangenheit |
| Release-Notes | **vollständig Deutsch und Englisch** |
| Release | Ein `0.14.0` für alle sechs Punkte |

## 1. Ausgangslage

- Store-Schema **v3** (`store.py`): `drinks`, `readings`, `wellbeing` +
  `wellbeing_history`, `total_ml_lifetime`, `inputs`, `archived_counts`;
  Migrationen v1→v2→v3, on-load idempotent.
- Backup **v1** (`backup.py`): `format`, `version`, `created`, `entries`
  (roher Store); **kein Restore**.
- Import (`importer.py`): CSV, Duplikat-Schutz `(ts, ml)` bzw. `(ts, sys, dia)`.
- UI: Panel (`panel-base/views/admin`) + Karte (`health-o-mat-card.js`), beide
  mit hartkodierten deutschen Texten; Entity-/Service-Übersetzungen de/en.
- Qualität: **812 Unit-Tests**, **15 E2E-Tests**, CI lint/tests/validate/E2E.
- Bestehende Langzeitstatistik: `drinks_today` (`total`), `lifetime_total`
  (`total_increasing`), Recorder-Metadaten-Migration `ml` → `mL`.

## 2. Zielbild 0.14.0

Nach 0.14.0 gilt:

1. Jede Buchung/Messung/Meldung ist **korrigierbar**: Verlauf, Void (löschen),
   Restore (wiederherstellen), Undo für alle drei Datentypen.
2. Jede Änderung ist **auditierbar** (wer/was/wann), ohne stille
   Datenüberschreibung.
3. Backups lassen sich **validiert und kontrolliert** zurückspielen — ganz,
   teilweise, mergend oder ersetzend, immer mit Dry-Run und Sicherheitsbackup.
4. Panel, Karte und Editor sind **de/en** über HAs Übersetzungsmechanismus.
5. Nutzer werden **erinnert** und bekommen einen **Wochenbericht**; Blueprints
   liefern erweiterbare Automationen.
6. Das Onboarding ist in **optionalen Schritten** mit Defaults abschließbar.
7. Einträge lassen sich **rückdatiert** erfassen (unbegrenzt in die
   Vergangenheit, nie in die Zukunft).

## 3. Architektur- und Datenmodell-Änderungen

### 3.1 Store-Schema v4 (Kern)

Neue Felder je Eintrag:

```text
id            stable UUID (string)
created_at    ISO-Zeitpunkt der ERFASSUNG (nicht der Messung)
ts            ISO-Zeitpunkt der Messung/Buchung (kann rückdatiert sein)
voided_at     ISO | null   (null = aktiv)
voided_by     user_id | null
void_reason   string | null
```

Neue Struktur je Person:

```text
audit_log: [
  {id, ts, action, kind, target_id, actor, details?}
]
wellbeing_entries: [
  {id, ts, key, created_at, voided_at, voided_by, void_reason}
]
```

- **Wellbeing** wird von „aktueller Wert + Historie" auf eine **Ereignisliste**
  umgestellt. `wellbeing`/`wellbeing_history` bleiben als abgeleitete
  Kompatibilitäts-Spiegel erhalten (für ältere Leser/Tests), sind aber nicht
  mehr die Quelle.
- **Aktueller Wohlbefindenswert** = letzter nicht-voided Eintrag.
- **Audit-Log** ist append-only. `details` enthält **keine** Gesundheitswerte
  (weder Mengen noch Wohlbefindens-Status), sondern nur Metadaten
  (z. B. `{"src": "button"}`, `{"reason": "Tippfehler"}`).
- **Actor** = `user_id` der WS-Verbindung bzw. `context.user_id` des Service-
  Aufrufs; bei Automationen `null`.
- **Retention** archiviert weiterhin aktive Einträge; voided Einträge bleiben
  im Haupt-Store. Das Audit-Log hat logische Append-only-Semantik und wird per
  Default bei **1000 Ereignissen pro Person** gekappt (Compaction entfernt nur
  die ältesten Ereignisse; ein `audit_pruned`-Summary-Event bleibt). Im Admin
  ist der Cap auf **unbegrenzt** (`0`) einstellbar. Diagnostics meldet
  Anzahl/Größe.
- **Kein Hard-Delete:** voided Einträge werden nie automatisch entfernt;
  vollständige Datenentfernung nur manuell über Store-Datei/Integration
  außerhalb der UI (dokumentiert, siehe §5.2).

Migration v3→v4 (idempotent):

1. Für `drinks`/`readings`: deterministische `id` (`uuid5` aus entry_id, kind,
   Index, ts), `created_at = ts`, `voided_at = null`, `void_reason = null`.
2. Für `wellbeing`: `wellbeing` + `wellbeing_history` chronologisch in
   `wellbeing_entries` überführen; IDs deterministisch; Legacy-Felder
   weiterführen.
3. `audit_log` anlegen (leer); optional ein `migration`-Event.
4. `schema = 4`.

### 3.2 Backup v2

- `BACKUP_VERSION = 2`; zusätzlich `schema` (Store-Schema), `persons`
  (Slug/Anzeigename), `counts`.
- Enthält vollständige `entries` inkl. `voided_*`, `audit_log` und
  `wellbeing_entries`.
- **Abwärtskompatibilität:** v1-Backups werden akzeptiert und beim Restore
  migriert. Neuere Versionen werden mit klarer Meldung abgelehnt.
- **Audit beim Restore:** importierte `audit_log`-Einträge werden standardmäßig
  **nicht** übernommen (keine fremde/gefälschte Audit-Historie); stattdessen
  neue `restore_backup`-Events geschrieben. Optional `restore_audit=true` für
  Experten (nur Admin, dokumentiert).

### 3.3 i18n über HA-Translations

- Kein eigenes i18n-Framework. UI-Texte liegen als **flache Schlüssel** im von
  hassfest erlaubten `common`-Bereich:
  `component.health_o_mat.common.ui_panel_<bereich>_<key>`.
- Frontend lädt sie über HAs WebSocket-Kommando
  `frontend/get_translations` (`category: "common"`, `integration:
  ["health_o_mat"]`, `language: hass.language`) und cached sie pro Sprache.
- Fallback: eingebettete de/en-Map; **nie** rohe Keys anzeigen.
- Entity-/Service-Übersetzungen bleiben unverändert HA-nativ.
- Datum/Zahlen/relative Zeit über `Intl`/`hass.locale`.
- Sprache wechselt zur Laufzeit (`hass.language`) → Neu-Rendern.

### 3.4 Optionen

Neue Options-Schlüssel (additiv, Defaults aus):

```text
reminders: {
  enabled, time, days, notify_service, quiet_hours,
  conditions: { drink_goal, no_drink_hours, bp_days, wellbeing_days }
}
weekly_report: {
  enabled, weekday, time, notify_service
}
audit_limit: 1000   # 0 = unbegrenzt (Admin-Einstellung)
```

- Options-Flow wird zu einem **Menü** mit optionalen Abschnitten:
  Grundlagen · Getränke · Wohlbefinden · Benachrichtigungen · Zusammenfassung.
- Bestehende Optionen bleiben erhalten (Merge-Pfad ist bereits umgesetzt).
- `audit_limit`: Default `1000`, im Admin auf `0` (unbegrenzt) oder einen
  anderen positiven Wert setzbar; Validierung `>= 0`.

### 3.5 Reminder-/Report-Engine

- `reminders.py`: Registrierung pro Config-Entry via
  `async_track_time_change`; Reload bei Options-Änderung; Dedup pro Tag.
- Bedingungen: Ziel nicht erreicht, keine Buchung seit X Stunden, keine
  BD-Messung seit X Tagen, keine Wohlbefindens-Meldung seit X Tagen.
- Zustellung: gewählter `notify.*`-Service, Fallback
  `persistent_notification`. Keine doppelten Notifications.
- `report.py`: HA-freie Berechnung + Markdown-Formatierung; Service
  `health_o_mat.weekly_report`; Versand **nur als Notification** (keine Datei);
  optional geplanter Versand.
- `blueprints/automation/health_o_mat/*.yaml`: Abend-Erinnerung,
  BD-Warnung, Wochenbericht; de/en-Beschreibungen, Person-Selektor.

## 4. Workstreams

### WS1 — Korrigierbarkeit: Verlauf, Void/Restore, Audit
**REQ (Vorschlag):** REQ-HOM-115 · **Aufwand:** L (6–8 Tage) · **Priorität:** P1

**Ziel:** Jede Buchung/Messung/Meldung ist sichtbar, löschbar (void),
wiederherstellbar (restore) und rückgängig zu machen; alle Änderungen sind
auditierbar.

**Backend**
- [ ] Store v4: IDs, `created_at`, `voided_*`, `audit_log`,
      `wellbeing_entries`; Migration v3→v4 + Tests.
- [ ] Helfer `active_entries()` / `active_wellbeing()`; alle Aggregate
      (heute, gestern, Prozent, Trends, Streak, BD-Ø, Koffein, Lifetime,
      Panel-Payload, Sensoren, Export, Import) filtern voided.
- [ ] `total_ml_lifetime` bei Void subtrahieren, bei Restore addieren; keine
      Rekomputation aus der aktivierten Historie (Archiv bleibt).
- [ ] `add_drink`/`add_reading`/`set_wellbeing` akzeptieren `ts` (WS6).
- [ ] `void_entry(entry_id, kind, id, actor, reason?)`,
      `restore_entry(...)`, `last_active_entry(...)`.
- [ ] WS: `list_history` (aktiv/voided, letzte 100), `void_entry`,
      `restore_entry`; `undo_last` um `kind=wellbeing` erweitern.
- [ ] Services: `void_entry`, `restore_entry`; `remove_last_entry` bleibt als
      Kompatibilitäts-Alias mit **Void-Semantik** (dokumentiert).
- [ ] Audit-Events für add/void/restore/import/retention/restore_backup.
- [ ] Audit-Cap: Default 1000 Ereignisse/Person, `audit_limit` im Admin
      (`0` = unbegrenzt); Pruning der ältesten Ereignisse mit
      `audit_pruned`-Summary; Diagnostics meldet Anzahl/Größe.
- [ ] `audit_limit` in `SETTINGS_KEYS`/`SETTINGS_SCHEMA`/`build_settings`
      (strikt int `>= 0`), Admin-Roundtrip getestet.

**Frontend**
- [ ] Panel: Verlaufsliste je Tab (letzte 100), Filter „aktiv/gelöscht",
      Löschen/Wiederherstellen mit Bestätigung; Undo für alle Typen.
- [ ] Karte: Undo für alle Typen; optionaler Verlauf (`show_history`, Default
      `false`, letzte 5) — Panel bleibt die vollständige Ansicht.
- [ ] Admin-Maske: `audit_limit` (Default 1000, `0` = unbegrenzt) inkl.
      Hilfetext und Validierung.
- [ ] Leerzustände und Fehlermeldungen de/en.

**Tests**
- [ ] Migration v1/v2/v3→v4, keine Datenverluste, deterministische IDs.
- [ ] Void/Restore für alle Typen; Aggregate/Lifetime/Streak/Trends korrekt.
- [ ] Wellbeing-Ereignisliste: aktueller Wert fällt nach Void auf Vorgänger.
- [ ] WS/Service-Berechtigungen, Actor im Audit-Log.
- [ ] Audit-Cap/Pruning: Default 1000, `0` = unbegrenzt, Summary-Event,
      Diagnostics-Zähler.
- [ ] JS: Verlauf/Undo/Filter; E2E: Drink löschen → aus „Heute" entfernt →
      wiederherstellen → Wert zurück.

**Akzeptanzkriterien**
- Kein stilles Überschreiben/Entfernen; jede Änderung hat ein Audit-Event.
- Gelöschte Einträge sind in allen abgeleiteten Werten nicht enthalten.
- Restore stellt den exakten Vorher-Zustand wieder her.
- `remove_last_entry` verliert keine Daten (Void statt Pop).
- Backup enthält Audit + voided Einträge; CSV exportiert standardmäßig nur
  aktive Einträge (dokumentiert).
- **Kein Hard-Delete in der UI**; Audit-Cap wirkt (Default 1000, `0` =
  unbegrenzt); voided Einträge bleiben erhalten.
- Verlauf/Undo in Panel und Karte; mobil bedienbar; de/en.

**Risiken**
- Langzeitstatistik des Recorders wird bei Korrekturen **nicht rückwirkend**
  korrigiert (dokumentieren; Recorder-Korrektur ggf. 0.15).
- Audit-Log ist per Default gekappt (1000); ältere Aktionen verlieren an
  Nachvollziehbarkeit. Admin kann auf unbegrenzt stellen (Wachstum).
- Voided Einträge wachsen ohne Hard-Delete; Monitoring/Compaction nötig.
- Wellbeing-Umbau berührt viele Leser (sorgfältige Regressionstests).
- **Archivierte Einträge** (Retention) erscheinen nicht im Verlauf; Korrekturen
  in 0.14 betreffen nur den Haupt-Store. Retention ist Default aus; im
  Verlauf/README klar kennzeichnen.

---

### WS2 — Backup-Restore inkl. Teil-Restore
**REQ (Vorschlag):** REQ-HOM-116 · **Aufwand:** L (5–7 Tage) · **Priorität:** P1

**Ziel:** Backups validiert, nachvollziehbar und kontrolliert zurückspielen.

**Backend**
- [ ] `restore.py` (HA-frei): `parse_backup_document`, `validate_backup`,
      `plan_restore`, `apply_restore_plan`.
- [ ] Modi: `merge` (Default) und `replace`; Filter: `persons`, `datasets`
      (`drinks`, `blood_pressure`, `wellbeing`), `from`/`to` (ISO), `dry_run`.
- [ ] Personen-Mapping `person_map: {source_slug: target_entry_id}`;
      unbekannte Person ohne Mapping → Fehler/Skip (kein Auto-Anlegen).
- [ ] Duplikat-Schutz: Getränke `(ts, ml, type)`, BD `(ts, sys, dia)`,
      Wohlbefinden `(ts, key)`; Merge überspringt Duplikate, Replace leert den
      gewählten Scope vorher.
- [ ] Pre-Restore-Sicherheitsbackup; atomisches Schreiben (Kopie validieren,
      dann ein Save); Rollback bei Fehler.
- [ ] Backup v2 + v1-Migration; Ablehnung neuerer Versionen.
- [ ] Admin-only Service `health_o_mat.restore_backup` und WS
      `restore_backup`; Audit-Event pro Person.
- [ ] Dry-Run liefert `{added, updated, skipped, conflicts, errors, persons}`.

**Frontend**
- [ ] Admin-Karte „Restore": Dateiauswahl aus
      `/config/health_o_mat_import/` (kein Browser-Upload), Modus, Filter,
      Personen-Mapping, Dry-Run-Ergebnis, Bestätigung (z. B. `RESTORE` /
      `REPLACE`), Sicherheitsbackup-Hinweis.
- [ ] De/en, Fokusmanagement, Fehlerzustände.

**Tests**
- [ ] Planungslogik: Merge/Replace, Duplikate, Filter, Mapping, Versionen.
- [ ] Apply: atomar, Pre-Backup, Audit, Rollback.
- [ ] Dry-Run schreibt nichts.
- [ ] E2E: Backup → Daten ändern → Merge-Restore; Teil-Restore einer Person;
      Replace nur im Scope; unbekannte Person mit Mapping.

**Akzeptanzkriterien**
- Restore ist ohne Datenverlust möglich; Dry-Run zeigt die Wahrheit.
- Replace ist auf den gewählten Scope begrenzt und doppelt bestätigt.
- Unbekannte Personen werden nie stillschweigend angelegt.
- V1-Backups funktionieren; kaputte/neuere Backups werden klar abgelehnt.
- Vor jedem echten Restore existiert ein Sicherheitsbackup.

**Risiken**
- Personen-Identität über Instanzen hinweg (Slug vs. Entry-ID).
- Replace-Semantik bei überlappenden Zeiträumen.
- Große Backups (Performance/Speicher).

---

### WS3 — UI-Internationalisierung de/en (HA-nativ)
**REQ (Vorschlag):** REQ-HOM-117 · **Aufwand:** L (4–6 Tage) · **Priorität:** P1

**Ziel:** Panel, Karte und Editor folgen der HA-Sprache (de/en), ohne eigenes
i18n-Framework.

**Umsetzung**
- [ ] Spike: `frontend/get_translations` mit `category: "common"` und
      `integration: ["health_o_mat"]` gegen die E2E-Instanz verifizieren.
- [ ] `common`-Schlüssel in `strings.json`, `translations/de.json`,
      `translations/en.json` (flach, Präfix `ui_panel_`, `ui_card_`,
      `ui_admin_`, `ui_editor_`).
- [ ] `ui_i18n.js` (Panel): Loader + Cache + `t(key, vars)` + Fallback-Map;
      Laden bei `hass`-Set und Sprachwechsel; Re-Render.
- [ ] Karte: kleiner inline Loader (Datei bleibt importfrei) mit gleichem
      Vertrag; Fallback de/en.
- [ ] Alle nutzersichtbaren Strings ersetzen (Panel-Views, Admin, Editor,
      Karte, Fehlermeldungen, Leerzustände, Bestätigungen).
- [ ] `relativeTime`/Datumsformate über `Intl` + `hass.language`.
- [ ] Tests: de/en-Parität, alle verwendeten Keys vorhanden, kein roher Key,
      Sprachwechsel, E2E mit `locale=en-US`.
- [ ] Doku: Übersetzungsbeitrag (nur `translations/*.json`, keine Logik).

**Akzeptanzkriterien**
- Englische HA-Instanz zeigt englische UI; Deutsch bleibt vollständig.
- Fehlende Übersetzung fällt sauber zurück, zeigt nie `ui_...`.
- `hassfest` bleibt grün (nur erlaubte `common`-Struktur).
- Entity-/Service-Übersetzungen unverändert; Paritätstest.
- Keine nutzersichtbaren hartkodierten deutschen Strings in Render-Pfaden
  (Test/Heuristik; Logs/Testdaten ausgenommen).

**Risiken**
- `common`-Kategorie/Timing des Frontend-Loaders.
- Karte ist importfrei → leichte Duplikation des Loaders.
- Übersetzungsdrift bei künftigen Features → Paritätstest + Review-Checkliste.

---

### WS4 — Erinnerungen, Wochenbericht, Blueprints
**REQ (Vorschlag):** REQ-HOM-118 · **Aufwand:** M–L (5–7 Tage) · **Priorität:** P1

**Ziel:** Nutzer werden zur richtigen Zeit erinnert und bekommen einen
verständlichen Wochenbericht; Automationen sind als Blueprints verfügbar.

**Backend**
- [ ] Options `reminders` + `weekly_report` (Defaults aus; Validierung).
- [ ] `reminders.py`: Scheduler (`async_track_time_change`), Reload bei
      Options-Änderung, Dedup pro Tag, Quiet Hours, Bedingungen.
- [ ] Zustellung: `notify.*` (Auswahl) oder `persistent_notification`;
      Fehler sichtbar, aber nicht setup-kritisch.
- [ ] `report.py` (HA-frei): Kennzahlen + Markdown; Service
      `health_o_mat.weekly_report`; Versand **nur als Notification** (keine
      Datei).
- [ ] Optional: geplanter Wochenbericht (Wochentag/Uhrzeit) über denselben
      Scheduler.
- [ ] Blueprints: Abend-Erinnerung, BD-Warnung, Wochenbericht;
      `blueprints/automation/health_o_mat/`.

**Frontend**
- [ ] Options-Menü „Benachrichtigungen" (de/en): Reminder an/aus, Zeit, Tage,
      Bedingungen, Notify-Service, Quiet Hours; Wochenbericht an/aus,
      Wochentag/Zeit (nur Notification).
- [ ] Admin-Panel: Hinweis/Status „Reminder aktiv", Test-Button
      („Testbenachrichtigung senden") — admin-only, kein Zwang.

**Tests**
- [ ] Bedingungslogik HA-frei; Scheduler mit `freezegun` (DST, Tageswechsel).
- [ ] Dedup/Quiet Hours; Notify-Fallback; Fehlerpfad.
- [ ] Report-Berechnung + Markdown-Golden-Test; Notification-Versand
      (keine Datei).
- [ ] Blueprint-YAML-Schema + de/en-Texte.
- [ ] E2E (optional): Reminder-Notification über gemockten Notify-Service.

**Akzeptanzkriterien**
- Reminder feuern nur bei erfüllter Bedingung, zur richtigen Zeit, ohne
  Duplikate; Quiet Hours respektiert.
- Wochenbericht als Service und (optional) geplant; Inhalt korrekt; Zustellung
  **nur als Notification** (keine Datei).
- Blueprints importierbar und valide; Person frei wählbar.
- Alle Einstellungen de/en; Defaults aus; keine Setup-Blockade.

**Risiken**
- Notification-Spam/Doppelungen; Scheduler-Lifecycle bei Reload.
- `notify`-Service-Auswahl ist instanzabhängig.
- DST/Zeitzone.

---

### WS5 — Onboarding/Options-Wizard mit optionalen Schritten
**REQ (Vorschlag):** REQ-HOM-119 · **Aufwand:** M (3–4 Tage) · **Priorität:** P1

**Ziel:** Neue Nutzer kommen mit Defaults in wenigen Schritten ans Ziel;
Fortgeschrittene erreichen alle Details.

**Umsetzung**
- [ ] Options-Flow als Menü: Grundlagen · Getränke · Wohlbefinden ·
      Benachrichtigungen · Zusammenfassung.
- [ ] Jeder Abschnitt optional: „Defaults übernehmen" / „Überspringen";
      Änderungen in `_pending`, Speichern erst in der Zusammenfassung.
- [ ] Zusammenfassung zeigt die Änderungen; „Speichern" schreibt gemergte
      Optionen (kein Verlust nicht angezeigter Keys).
- [ ] Neue Config-Entries: Name → optionaler Hinweis „Jetzt einrichten?" mit
      Defaults; sonst später über Optionen.
- [ ] Defaults zentral: `DEFAULT_QUICK_DRINKS`, `DEFAULT_DRINK_LEXICON`,
      leere Bilder, `wellbeing_confirm=false`, Reminders aus.
- [ ] Tests: Skip/Defaults je Schritt, keine Datenverluste, bestehende
      Optionen bleiben, Menü-Navigation, de/en.
- [ ] Doku/README: „In 2 Minuten starten".

**Akzeptanzkriterien**
- Neuer Nutzer kann mit Defaults in ≤2 Schritten abschließen.
- Jeder optionale Schritt ist überspringbar; Defaults werden angewandt.
- Bestehende Optionen (inkl. `wellbeing_confirm`) bleiben unverändert.
- Zusammenfassung vor dem Speichern; Abbrechen ändert nichts.
- Bestehende Entries funktionieren unverändert.

**Risiken**
- HA-Options-Flow-Menü-API/Versionen.
- Komplexität der `_pending`-Zusammenführung.
- Bestehende Tests, die Schrittfolgen erwarten.

---

### WS6 — Rückdatieren (unbegrenzt)
**REQ (Vorschlag):** REQ-HOM-120 · **Aufwand:** M (3–4 Tage) · **Priorität:** P1

**Ziel:** Vergessene Einträge lassen sich mit korrektem Zeitpunkt nachtragen.

**Backend**
- [ ] Services `add_drink`, `add_blood_pressure`, `set_wellbeing` und WS-
      Kommandos um optionales `ts`/`timestamp` erweitern (ISO, tz-aware).
- [ ] Validierung: nicht in der Zukunft (> jetzt + 5 min Toleranz), nicht vor
      1900; ungültige/naive Zeitstempel klar ablehnen bzw. lokal interpretieren
      (dokumentiert).
- [ ] `created_at` (Erfassung) getrennt von `ts` (Messung) speichern.
- [ ] Historie/JSON nach `ts` sortiert; „letzter Eintrag" für Undo = zuletzt
      **erfasst** (Insertion Order), nicht größter `ts`.
- [ ] Alle Tages-/Wochen-/Streak-Aggregate nutzen `ts` (bereits on-read).

**Frontend**
- [ ] Datum/Zeit-Feld (`datetime-local`) in Getränke-, BD- und
      Wohlbefinden-Formularen; Default „jetzt".
- [ ] Schnellwahl: „Jetzt", „Vor 1 h", „Gestern" + freies Datum/Zeit.
- [ ] Anzeige: relativ für neu, absolut für älter; Zeitzone korrekt.
- [ ] Mobile: `datetime-local`-Bedienung, keine überlappenden Labels.

**Tests**
- [ ] Future-Ablehnung; tz-aware/naive; DST; Tagesgrenze.
- [ ] Rückdatierter Drink zählt am richtigen Tag, in Trend/Streak/Lifetime.
- [ ] Undo entfernt den zuletzt erfassten, nicht den zeitlich letzten Eintrag.
- [ ] Services/WS mit `ts`; Import/Export-Roundtrip.
- [ ] E2E: „Gestern" buchen → erscheint in Gestern, nicht Heute.

**Akzeptanzkriterien**
- Rückdatieren funktioniert für alle drei Datentypen, unbegrenzt zurück.
- Zukunft wird verständlich abgelehnt.
- Aggregate, Charts und Reports verwenden den gewählten Zeitpunkt.
- Undo-Semantik ist dokumentiert und getestet.
- UI bleibt mobil bedienbar; de/en.

**Risiken**
- Zeitzonen/DST und naive Eingaben.
- Verwirrung „Messzeit vs. Erfassungszeit" → UI-Hinweis.
- Recorder-Langzeitstatistik bei rückdatierten Änderungen (siehe WS1).

## 5. Querschnittsthemen

### 5.1 Migration & Kompatibilität

- Store v3→v4 idempotent; Migrationskette erweitern; Tests mit v1/v2/v3-
  Fixtures.
- Backup v1→v2; v1 bleibt lesbar; v2 wird geschrieben.
- Keine Änderung an `unique_id`s, Entity-IDs oder Config-Entry-`data`.
- Options additiv; bestehende Keys bleiben; Merge-Pfad bereits vorhanden.
- Services/WS: neue Felder optional; `remove_last_entry` bleibt, Semantik
  dokumentiert (Void statt Entfernen).

### 5.2 Datenschutz & Sicherheit

- Restore/Settings/Export/Backup bleiben **admin-only**, serverseitig geprüft.
- Restore liest nur aus `/config/health_o_mat_import/` (Whitelist, kein
  Browser-Upload, nie `/config/www`).
- Audit-Log: minimal (IDs/Zeit/Aktion/Actor), keine Secrets; Diagnostics
  zählen nur.
- Pre-Restore-Backup; atomisches Schreiben; Rollback.
- **Kein Hard-Delete in der UI** (Entscheidung 2026-10-25): Löschen = Void,
  Wiederherstellen = Restore. Vollständige Datenentfernung nur manuell über
  Store-Datei/Integration außerhalb der UI; die DSGVO-Abwägung bleibt als
  dokumentiertes Restrisiko. Audit-Cap Default 1000, im Admin unbegrenzt.
- Audit-Cap/Pruning ist eine **Kompaktierung**, kein inhaltliches Löschen von
  Gesundheitsdaten; das `audit_pruned`-Summary bleibt nachvollziehbar.

### 5.3 Barrierefreiheit

- Verlauf als semantische Liste/Tabelle mit Buttons und `aria-label`.
- Bestätigungen fokussierbar, Fokus nach Aktion gesetzt, `aria-live` für
  Status.
- Keine reine Emoji-/Farb-Information; Labels bleiben sichtbar (auch mobil).
- Tabs: `aria-controls` + Pfeilnavigation (kann in WS1/WS3 mitlaufen).

### 5.4 Performance & Stabilität

- Kein Polling; Scheduler nur bei aktiven Reminders.
- Historie-Limits (100 Panel, 5 Karte, 1000 Audit-Events pro Person als
  Dokumentation; keine Auto-Löschung in 0.14).
- Große Backups: Streaming/Executor, Größenlimit mit klarer Meldung.
- Migrationen laufen on-load, setup-kritisch nur bei Fehler (Recovery-Pfad
  bleibt).

### 5.5 Tests & CI

- Unit-Suite HA-frei bleibt Pflicht; neue Logik (Restore-Planung, Report,
  Reminder-Bedingungen, Zeitfenster) HA-frei.
- JS-Tests für Verlauf/Undo/Backdate/i18n.
- E2E: neue Fälle für WS1/WS2/WS3/WS5/WS6; Reminder optional.
- CI: `ruff check .`, `ruff format --check .`, `pytest -q`, hassfest/HACS,
  E2E; Release-Gates.

### 5.6 Dokumentation

- `README.md`: neue Funktionen, Restore-Anleitung, Backdating, i18n,
  Lösch-/Audit-Semantik, Migrationshinweise.
- `docs/REQUIREMENTS.md`: REQ-HOM-115…120 mit Akzeptanzkriterien und Belegen.
- `docs/IDEATION-VISION.md`: Querverweis auf den Plan.
- Release Notes: Summary, Features, Breaking Changes (Void-Semantik,
  Backup v2), Migration, Full Changelog — **vollständig Deutsch und Englisch**.

## 6. Meilensteine & Sequenz

| Meile | Inhalt | Dauer (Richtwert) |
|---|---|---|
| **M0 — Spikes/ADRs** | i18n `common` + `frontend/get_translations`; Store-v4-Design; Restore-Plan; Reminder-Scheduler; Options-Menü | 1–2 Tage |
| **M1 — Fundament** | Store v4 + Audit/IDs/Wellbeing-Events + Migration; `created_at`/`ts`; Backup v2; i18n-Loader + String-Inventar | 5–7 Tage |
| **M2 — Backend** | History/Void/Restore; Restore-Engine; Reminder/Report; Options-Wizard-Backend | 7–9 Tage |
| **M3 — Frontend** | Panel-Verlauf/Undo/Backdate; Karte; Admin-Restore/Reminders/Report; i18n alle Flächen; Wizard-UI | 7–9 Tage |
| **M4 — Härtung/Release** | E2E, Doku, Review, Release 0.14.0 | 3–5 Tage |

**Kritischer Pfad:** M0-i18n → M1-Store → M2-Backend → M3-UI → M4.
**Parallelisierbar:** i18n-String-Inventar, Blueprints, Report-Logik,
Dokumentation, Tests.

## 7. Testmatrix (Auszug)

| Bereich | Unit | JS | E2E |
|---|---|---|---|
| Store v4/Migration | ✅ | — | — |
| Void/Restore/Audit | ✅ | ✅ | ✅ |
| Audit-Cap/Pruning (`audit_limit`) | ✅ | — | — |
| Aggregate/Lifetime/Streak | ✅ | — | ✅ |
| Restore Merge/Replace/Teil/Dry-Run | ✅ | — | ✅ |
| Backup v1/v2 | ✅ | — | ✅ |
| i18n de/en/Parität | ✅ | ✅ | ✅ (en-US) |
| Reminder-Bedingungen/Scheduler | ✅ | — | optional |
| Wochenbericht | ✅ | — | optional |
| Blueprints | ✅ (YAML) | — | — |
| Onboarding Skip/Defaults | ✅ | — | ✅ |
| Backdating/TZ/DST | ✅ | ✅ | ✅ |
| Regression Bestand | ✅ (812+) | ✅ | ✅ (15+) |

## 8. Release 0.14.0

- **Version:** `0.14.0` (MINOR; keine Entity-/`unique_id`-Änderung).
- **Cache-Buster:** alle `?v=0.13.0` → `?v=0.14.0`, `manifest.version`
  synchron.
- **Migration:** Store v4, Backup v2; v1-Backups bleiben lesbar.
- **Breaking Changes in den Notes klar nennen:**
  - „Löschen" ist jetzt **Void** (Eintrag bleibt im Audit/Backup, zählt aber
    nicht mehr in Auswertungen); **kein Hard-Delete in der UI**.
  - Audit-Log Default **1000 Ereignisse/Person**; im Admin unbegrenzt (`0`).
  - `remove_last_entry` entfernt nicht mehr hart, sondern voidet.
  - CSV exportiert standardmäßig nur aktive Einträge.
  - Backup-Format v2 (v1 wird weiter akzeptiert).
- **Release-Dreiklang:** Commit → Tag `v0.14.0` → GitHub Release
  (Summary, ✨ Features, 💥 Breaking Changes, Full Changelog) — **vollständig
  auf Deutsch und Englisch**.
- **DoD:** Code-Review, Validator, E2E grün, Doku, keine Regressionen.

## 9. Vorgeschlagene REQ-Zuordnung

| REQ | Titel | WS |
|---|---|---|
| REQ-HOM-115 | Korrigierbarkeit: Verlauf, Void/Restore, Audit-Log | WS1 |
| REQ-HOM-116 | Backup-Restore inkl. Teil-Restore und Dry-Run | WS2 |
| REQ-HOM-117 | UI-Internationalisierung de/en über HA-Translations | WS3 |
| REQ-HOM-118 | Erinnerungen, Wochenbericht und Blueprints | WS4 |
| REQ-HOM-119 | Onboarding/Options-Wizard mit optionalen Schritten | WS5 |
| REQ-HOM-120 | Rückdatierte Einträge (unbegrenzt) | WS6 |

> Die REQ-Einträge werden nach Freigabe dieses Plans in
> `docs/REQUIREMENTS.md` aufgenommen (Akzeptanzkriterien + Belege).

## 10. Entschiedene Punkte & Restrisiken

Die zuvor offenen Punkte sind entschieden:

1. **Löschen:** **kein Hard-Delete in der UI** (dauerhaft); Void/Restore +
   Audit-Log.
2. **Karten-Verlauf:** `show_history` Default **aus**; Panel zeigt den vollen
   Verlauf.
3. **Reminder-Kanäle:** beliebiger `notify.*`-Service, Fallback
   `persistent_notification`.
4. **Wochenbericht:** **nur Notification** (Markdown), keine Datei.
5. **Audit-Aufbewahrung:** Default **Cap 1000 Ereignisse/Person**, im Admin
   **unbegrenzt** (`0`) einstellbar.
6. **Release-Notes:** **vollständig Deutsch und Englisch**.

**Restrisiken (dokumentiert, kein Startblocker):**

- **DSGVO/Löschpflicht:** Vollständige Datenentfernung nur manuell über
  Store-Datei/Integration außerhalb der UI. Vor einer öffentlichen 1.0 erneut
  bewerten.
- **Voided Einträge wachsen** ohne Hard-Delete; Monitoring/Compaction nötig.
- **Audit-Cap 1000** kann die Nachvollziehbarkeit älterer Aktionen begrenzen;
  Admin kann auf unbegrenzt stellen (Speicherwachstum).
- **Recorder-Langzeitstatistik** wird bei Korrekturen nicht rückwirkend
  angepasst (dokumentierte Grenze).

## 11. Nicht in diesem Plan

- P1-Punkt 3 (Mehrbenutzer/ACL, Datenschutzmodell) — eigenes Paket 0.15.
- Volles Bearbeiten von Einträgen (Wert/Typ ändern) — Verlauf + Void/Restore
  reichen für 0.14.
- Medikamente, Schlaf, Gewicht, Aktivität, Geräte-Integrationen — Vision,
  nicht 0.14.
- PDF-Arzt-Export, KI-Funktionen, Anomalie-Erkennung — 0.15+.
- Rückwirkende Recorder-Langzeitstatistik-Korrektur — dokumentierte Grenze.

## 12. Definition of Done (0.14.0)

- [ ] Alle sechs REQs umgesetzt und in `docs/REQUIREMENTS.md` belegt.
- [ ] Store-v4-/Backup-v2-Migrationen idempotent und getestet.
- [ ] Keine Regression: Unit-, JS- und E2E-Suite grün.
- [ ] `ruff check .` und `ruff format --check .` clean.
- [ ] de/en vollständig; `hassfest`/HACS grün.
- [ ] Audit-Cap Default 1000, Admin `0` = unbegrenzt; Diagnostics-Zähler.
- [ ] README/Release Notes mit Migration und Breaking-Change-Hinweisen
      (vollständig Deutsch **und** Englisch).
- [ ] Code-Review ohne Blocker; Validator/DoD erfüllt.
- [ ] Release `v0.14.0` mit Tag ↔ `manifest.version` synchron.

# Entscheidungsprotokoll: Multi-Unit-Speicherung/-Konvertierung (Labor)

**Was dies dokumentiert:** Die vier Architekturentscheidungen (Q1–Q4), die der
Nutzer zur Analyse in `docs/concept-multi-unit-conversion-plan.md` getroffen
hat, sowie die daraus im Branch `feat/lab-multiunit-validation-hardening`
tatsächlich umgesetzten Schritte.
**Scope:** Nur Labor-Domäne (Area `labs`); Trinken/Blutdruck sind explizit
nicht Teil dieser Entscheidungen (siehe Q2).
**Zeitraum/Stand:** 2026-11-20, Branch `feat/lab-multiunit-validation-hardening`
(5 Commits, Basis `main` nach `9e7e5b2`'s Vorgänger-Historie; noch nicht
gemerged, noch kein Release).
**Datenquelle:** `docs/concept-multi-unit-conversion-plan.md` (Analyse, Optionen
A/B/C, §4 offene Fragen, §6 Nutzerentscheidungen), `docs/REQUIREMENTS.md`
(REQ-HOM-135), `git log` auf diesem Branch, `.tmp/impl-progress.md`
(Umsetzungsnarrativ je Schritt).
**Vorbild/Format:** `docs/PLAN-AUDIT-2026-11-03.md` §5 „Offene Entscheidungen".
**Entscheider:** Nutzer — Entscheidung relayed über den Koordinator
(`main_chat`/`orchestrator`), nicht durch dieses Dokument selbst getroffen.

---

## 1. Entscheidungstabelle (Q1–Q4)

| ID | Frage (verbatim/sinngemäß aus dem Konzeptdokument) | Abgewogene Optionen | Entscheidung | Entscheider | Wirkung |
|---|---|---|---|---|---|
| Q1 | Haupt-Entity + abgeleitete Read-Only-View-Entities pro Alt-Einheit — macht das Sinn, und wie passt das zu `unique_id`/`device_info`/HACS-Konventionen? (`concept-multi-unit-conversion-plan.md` §4 Q1, verbatim zitiert) | **A** On-Read-Konvertierung generalisieren (kein neuer Entity-Typ, neuer Lese-Pfad mit Einheiten-Parameter) · **B** Mehrfach-Persistenz nach Lab-Vorbild (kanonisch + `reported_*`) · **C** Haupt-Entity + abgeleitete Read-Only-View-Entities je Alt-Einheit | **Kombination A+B**: On-Read-Konvertierung als Basismechanik, zusätzlich der bereits bestehende `reported_value`/`reported_unit`-Mechanismus bei Lab-Readings als Audit-Trail. **C ausdrücklich verworfen** — Entity-Zuwachs (20–40+ neue Entities/Person) und Breaking-Change-Risiko bei jeder künftigen Änderung der Ableitungs-Entity-Menge widersprechen Anforderung 2 (manuelle Erweiterbarkeit ohne starres System) | Nutzer, relayed über Koordinator | Entblockt Schritt 4 (Konzeptplan §3); keine neuen Plattform-/Entity-Dateien, kein `unique_id`-Schema-Entwurf nötig |
| Q2 | Gilt die Multi-Unit-Persistenz-Anforderung für alle Domänen (Trinken/BP/Labor) oder nur Labor? (§4 Q2) | **Alle Domänen** (neues Einheiten-Vokabular auch für Volumen/Druck) · **Nur Labor** (Trinken/BP bleiben rein kanonisch) | **Nur Labor** für diese Umsetzung. Architektur bleibt bewusst so gebaut, dass Trinken/BP später ergänzbar sind — aber nichts dafür wurde in diesem Schritt gebaut | Nutzer, relayed über Koordinator | Schritt 4 bleibt auf `ws_api.py`/`logic.py`/Labor-Store-Felder begrenzt; kein neues Volumen-/Druck-Einheiten-Vokabular |
| Q3 | Wo soll der „manuell erweiterbare" Einheiten-/Faktor-Katalog liegen? (§4 Q3) | **(a)** weiterhin `const.py` (Code, Release-gebunden) · **(b)** `entry.options` (pro Person, release-frei) · **(c)** eigene JSON/YAML-Konfigurationsdatei im Integrationsverzeichnis | **Bleibt in `const.py`** (`LAB_MARKERS`/`LAB_DEFAULT_UNITS`/`alt_units`). Keine Verlagerung nach `entry.options` oder in eine externe Konfigurationsdatei. „Manuell erweiterbar" heißt hier: Hand-Edit im Code über ein Release — nicht release-frei | Nutzer, relayed über Koordinator | Kein Options-Schema-Umbau, kein neues Config-Dateiformat, kein Backup-/Restore-Impact für den Katalog selbst |
| Q4 | Soll der Test-Coverage-Fix (grounded B-2) auch die 29 Marker ohne `alt_units` einschließen, oder reichen die 22 mit echten `alt_units`? (§4 Q4) | **Nur 22 Marker mit nicht-leeren `alt_units`** · **Alle 41 `LAB_MARKERS`** (inkl. trivialer Faktor-1-Selbstkonversion) | **Alle 41 Marker.** Oracle-Test deckt auch die trivialen Faktor-1-Fälle ab, damit ein künftig nachgerüsteter `alt_units`-Eintrag automatisch mitgeprüft wird | Nutzer, relayed über Koordinator | Schritt 2 (Lab-Oracle-Test) iteriert über `LAB_MARKERS` vollständig statt über eine gefilterte Teilmenge |

---

## 2. Konsequenz: was auf dieser Grundlage umgesetzt wurde

Fünf Commits auf `feat/lab-multiunit-validation-hardening` (chronologisch):

| Commit | Beschreibung | Bezug zu den Entscheidungen oben |
|---|---|---|
| `9e7e5b2` | fix: unify daily_goal_ml bounds and add input length limits | Unabhängig von Q1–Q4 — grounded Audit-Befunde B-1/C-1 + Längenlimit-Teil von C-2 (Konzeptplan §0, §3 Schritt 1); keine Multi-Unit-Berührung |
| `9351b95` | test: cover all 41 lab markers in JS/Python oracle parity | Direkte Umsetzung von **Q4** (alle 41 Marker statt nur 22) — Konzeptplan §3 Schritt 2 |
| `4e0ad0c` | test: source wellbeing-mirror parity expectations from logic.py | Unabhängig von Q1–Q4 — grounded Audit-Befund B-3 (Konzeptplan §3 Schritt 5); gleiche Fehlerklasse (JS-Spiegel-Drift) wie Schritt 2, aber kein Einheiten-Thema |
| `71a05b2` | feat: add multi-unit read path for lab values | Direkte Umsetzung von **Q1** (Kombination A+B) und **Q2** (Scope nur Labor) und **Q3** (Katalog bleibt `const.py`, keine Verlagerung) — Konzeptplan §3 Schritt 4. Neues WS-Kommando `health_o_mat/get_lab_value` (`ws_api.py`), kein Store-Schema-Bump, keine neue Entity, kein neues Einheiten-Vokabular für Trinken/BP |
| `40a472c` | docs: add REQ-HOM-135 for lab multi-unit read path | Dokumentiert die Konsequenz von Commit `71a05b2` als eigene Anforderung — **REQ-HOM-135**, `docs/REQUIREMENTS.md` |

### REQ-HOM-135 — Bezug

`docs/REQUIREMENTS.md` §„REQ-HOM-135 — Produktiver Multi-Unit-Lese-Pfad für
Laborwerte (WS-Kommando `get_lab_value`)": widerruft gezielt den Teil des
REQ-HOM-134-Nicht-Ziels „kein Produktionsaufrufer" für
`convert_lab_display_value()`/`lab_display_decimals()`, ausschließlich für den
neuen WS-Pfad; Store, Sensor-State, `native_unit_of_measurement`, CSV-Export
und Entity-Menge bleiben laut REQ-HOM-135 unverändert kanonisch. Vier
Akzeptanzkriterien, alle als erfüllt markiert (`[x]`); Belege:
`custom_components/health_o_mat/ws_api.py` (`COMMAND_GET_LAB_VALUE`,
`websocket_get_lab_value`, `_match_lab_target_unit`) und 7 Tests in
`tests/test_ws_api.py` (Abschnitt „`get_lab_value` (Multi-Unit-Lese-Pfad,
Schritt 4)").

**Status zum Zeitpunkt dieses Protokolls:** REQ-HOM-135 ist laut
`docs/REQUIREMENTS.md` als „Umgesetzt (noch kein Release)" markiert — kein
Versions-Bump, `manifest.json` unverändert. Dieses Protokoll trifft keine
neue Entscheidung über Release-Zeitpunkt oder -Nummer.

---

## 3. Was dieses Protokoll nicht abdeckt (Scope-Disziplin)

- **Keine Umsetzung für Trinken/BP** — per Q2 bewusst ausgeschlossen, kein
  Gegenstand dieses Branches.
- **Kein Entity-/`unique_id`-Schema für Option C** — verworfen (Q1), daher
  nicht dokumentiert, weil nicht gebaut.
- **Kein Umbau des Katalog-Speicherorts** — per Q3 nicht verändert.
- **Kein Release-Entscheid** (Tag/Version) — liegt außerhalb dieses
  Entscheidungsbündels; siehe Status-Hinweis in REQ-HOM-135.
- **Schritt 1 (`daily_goal_ml`/Längenlimits) und Schritt 5 (Wellbeing-Oracle)**
  sind in der Commit-Tabelle oben nur der Vollständigkeit halber referenziert
  (sie liefen im selben Branch) — sie sind keine Konsequenz von Q1–Q4, sondern
  eigenständige, davor schon im Konzeptplan §0/§3 begründete Schritte.

---

*Dieses Dokument beschreibt den Stand des Branches zum protokollierten Datum
(2026-11-20). Es wird nicht rückwirkend für künftige Branches/Releases
fortgeschrieben — eine spätere Änderung an Q1–Q4 (z. B. Aufnahme von
Trinken/BP) bekommt ein eigenes, neues Entscheidungsprotokoll statt einer
Überschreibung dieses hier (Versionshygiene).*

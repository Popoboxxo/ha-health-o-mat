# Vision 2026–2029 — HA Health-O-Mat

**Status:** Entwurf (2026-10-25) · **Zielgruppe:** Maintainer + Community ·
**Horizont:** 2–3 Jahre · **Verwandt:** `docs/REQUIREMENTS.md`,
`docs/PLAN-UX-P1.md`, `docs/IDEATION-UI-PRO.md`

> Dieses Papier beschreibt, wohin sich HA Health-O-Mat entwickeln soll. Es ist
> kein Versprechen und keine Zusage an einzelne Releases: Reihenfolge, Umfang
> und Detailtiefe können sich mit Nutzerfeedback, HA-Änderungen und
> Geräte-APIs ändern. Verbindliche Anforderungen entstehen erst als REQ in
> `docs/REQUIREMENTS.md`.

## 1. Vision in einem Satz

**Ein lokales, vertrauenswürdiges Gesundheits-Tagebuch für Home Assistant, das
wichtige Gesundheitsdaten ohne Cloud-Zwang erfasst, verständlich auswertet und
Menschen befähigt, ihre eigenen Muster zu erkennen — ohne medizinische
Diagnosen zu stellen.**

## 2. Warum es dieses Projekt gibt

- **Datenhoheit:** Gesundheitsdaten gehören den Nutzern. Speicherung,
  Auswertung und Export laufen lokal in Home Assistant; kein Konto, kein
  Cloud-Sync, keine Werbe- oder Verkaufslogik.
- **Alltagstauglichkeit:** Erfassen muss in Sekunden gehen — per Karte, Panel,
  Automation, Sprache oder NFC. Wer erst ein Formular suchen muss, hört auf.
- **Verstehbarkeit:** Rohwerte allein helfen wenig. Trends, Korrelationen und
  gut formulierte Reports machen aus Daten Erkenntnisse.
- **Home-Assistant-Nativität:** Entities, Services, Automationen, Dashboards
  und Langzeitstatistik sind die erste Bürger — keine Insellösung.
- **Vertrauen:** Backup/Restore, Auditierbarkeit, nachvollziehbare Löschregeln
  und ein sauberes Mehrbenutzer-Modell sind Grundlage, nicht Nachgedanke.

## 3. Für wen wir bauen

| Persona | Bedürfnis | typische Nutzung |
|---|---|---|
| **Einzelnutzer:in** | Schnell trinken/Blutdruck/Wohlbefinden erfassen, Verlauf sehen | Karte auf dem Handy-Dashboard, Panel am Desktop |
| **Familie/Haushalt** | Mehrere Personen, getrennte Sichten, keine Vermischung | Panel mit Personen-Kacheln, Pro-Person-Automationen |
| **Menschen mit chronischer Erkrankung** | Verlässliche Verlaufsdaten, Arzt-Export, Zusammenhänge erkennen | tägliche Messungen, Wochenbericht, CSV/PDF für die Praxis |
| **Pflegende Angehörige** | Fremde Person mitpflegen, klare Berechtigungen | mehrere Personen, Rollen/ACL (Zielbild) |
| **HA-Power-User** | Alles automatisierbar, lokal, offen | Services, Blueprints, MQTT, eigene Dashboards |
| **Datenschutzsensible** | Keine Cloud, keine Telemetrie, nachvollziehbare Löschung | lokaler Betrieb, Void/Restore + Audit-Log |

## 4. Leitplanken (nicht verhandelbar)

1. **Local-first.** Keine Cloud-Pflicht, keine implizite Telemetrie. Cloud-
   oder KI-Funktionen nur opt-in, klar gekennzeichnet und abschaltbar.
2. **Keine medizinische Beratung.** Wir klassifizieren und visualisieren; wir
   diagnostizieren oder therapieren nicht. Disclaimer bleibt sichtbar.
3. **Datenhoheit & Löschbarkeit.** Export in offenen Formaten; Backup **und**
   Restore; Void/Restore mit Audit-Log. Vollständige Entfernung der Store-Datei
   bleibt ein dokumentierter manueller Weg außerhalb der UI (bewusste
   Entscheidung: kein Hard-Delete in der UI).
4. **HA-nativ.** Entities, Services, Automationen, Übersetzungen und
   Statistik-Mechanismen von HA nutzen, statt eigene Parallelwelten.
5. **Barrierearm.** Tastaturbedienung, Screenreader-Labels, ausreichende
   Kontraste, keine reine Farb-/Emoji-Kommunikation, mobile-first.
6. **Mehrsprachig ab Tag 1.** Deutsch und Englisch vollständig; weitere
   Sprachen über die HA-Community, ohne Fork.
7. **Keine stillen Breaking Changes.** `unique_id`s, Entity-IDs und
   Nutzerdaten bleiben stabil; Migrationen sind versioniert und idempotent.
8. **Erklärbar.** Jede Kennzahl (Score, Pace, WHO-Kategorie, Koffein) hat eine
   kurze, auffindbare Erklärung und eine erkennbare Unsicherheit.
9. **Open Source & Community.** HACS-fähig, dokumentierte Entscheidungen,
   nachvollziehbare Releases, Beiträge willkommen.
10. **Keine Monetarisierung.** Keine Ads, keine Datenverkäufe, keine
    Bezahl-Features, die Grundfunktionen künstlich beschneiden.

## 5. Themenfelder 2026–2029

### 5.1 Erfassen — breiter und reibungsloser

**Ziel:** Von drei Datentypen zu einem glaubwürdigen persönlichen
Gesundheitsbild, ohne die Eingabe zu erschweren.

- **Heute:** Getränke, Blutdruck, Wohlbefinden
- **Nächste Ausbaustufen:**
  - Medikamente/Supplements inkl. Dosis, Einnahmezeit, Adhärenz
  - Schlaf (Dauer, Qualität, Einschlafzeit)
  - Gewicht/Körpermaße
  - Aktivität/Schritte/ruhender Puls
  - Symptome/Schmerz, Krankheitsepisoden, Temperatur, SpO₂
  - Zyklus/Menstruation
  - Laborwerte mit Referenzbereichen
  - Alkohol/Zucker/Kalorien (aus Getränken ableitbar)
- **Kanäle:** Karte, Panel, Services, Automationen, Blueprints, Sprache
  (Alexa/Google), NFC/QR, Widgets, Smart-Bottle-/Geräte-Import.
- **Korrektur:** Verlauf, Bearbeiten, Void/Restore, Rückdatieren, Audit-Log.

### 5.2 Verstehen — von Daten zu Erkenntnissen

**Ziel:** Nicht nur zeigen, was war, sondern helfen, Muster zu erkennen.

- **Korrelationen:** Trinken ↔ Wohlbefinden, Koffein ↔ Schlaf/Blutdruck,
  Blutdruck ↔ Tageszeit/Medikation, Aktivität ↔ Schlaf.
- **Personalisierte Ziele:** Hydration nach Gewicht/Aktivität/Wetter,
  Blutdruck-Zielbereich, Wohlbefindens-Ziel.
- **Reports:** Wochen-/Monatsbericht, Arzt-Export (PDF/Markdown), optional
  automatisch per Notification.
- **Anomalien:** „Blutdruck steigt seit 3 Wochen", „seit 5 Tagen keine
  Wohlbefindens-Meldung", „Koffein heute über deinem Üblich".
- **Erklärbarkeit:** Jede Kennzahl mit Kurz-Legende, Datenbasis und
  Unsicherheitshinweis.

### 5.3 Verbinden — Geräte, Dienste, Community

**Ziel:** Manuelle Eingaben reduzieren, ohne Abhängigkeit von einer Cloud.

- **Geräte:** Withings, Omron, Apple Health/Health Connect, Garmin, Fitbit,
  Smart Bottles — bevorzugt lokal oder über HA-Integrationen.
- **HA-nativ:** MQTT, vorhandene Sensoren, Template-/Automation-Import.
- **Teilen:** Export für Arzt/Partner; keine automatische Weitergabe.
- **Community:** Blueprint-Bibliothek, Übersetzungen, Beispiel-Dashboards.

### 5.4 Vertrauen — Privacy, Audit, Mehrbenutzer

**Ziel:** Das System muss auch in Haushalten und bei sensiblen Daten
vertrauenswürdig sein.

- **Backup + Restore:** versioniert, validiert, Dry-Run, Merge/Replace,
  Teil-Restore pro Person/Datensatz/Zeitraum.
- **Audit-Log:** append-only Ereignisse (wer/was/wann), ohne stille
  Datenänderung; Void/Restore statt stillem Überschreiben.
- **Löschen:** kein Hard-Delete in der UI (Entscheidung 2026-10-25). Löschen
  ist Void, Wiederherstellen ist Restore. Das Audit-Log ist append-only (mit
  dokumentierter Kompaktierung) und standardmäßig auf 1000 Ereignisse pro
  Person begrenzt (im Admin unbegrenzt einstellbar). Vollständige Datenentfernung nur durch Löschen der
  Store-Datei/Integration außerhalb der UI; die DSGVO-Abwägung bleibt ein
  dokumentiertes Restrisiko für eine öffentliche 1.0.
- **Mehrbenutzer/ACL:** pro HA-Nutzer eigene Person(en), Admin nur für
  Verwaltung; klare Rechte für Alltag vs. Settings.
- **Sicherheit:** keine Secrets in Diagnostics/Exporten, private Pfade,
  serverseitige Rechteprüfung.

### 5.5 Zugänglich — UX, Sprache, Mobile

**Ziel:** Jede Funktion in wenigen Sekunden erreichbar, auf jedem Gerät.

- Vollständige **de/en**-Übersetzung über HA-Translations; weitere Sprachen
  später.
- Mobile-first: große Tap-Ziele, keine versteckten Labels bei kleinen Screens.
- Tastatur/Screenreader: Tabs mit Pfeilnavigation, Fokusmanagement,
  `aria-live` für Statusmeldungen.
- Onboarding in optionalen Schritten mit sinnvollen Defaults.
- In-App-Hilfe/Legenden statt README-Suche.

### 5.6 Plattform — Qualität und Wartbarkeit

- HA-Versionskompatibilität, hassfest/HACS-CI, ruff check + format.
- Unit-Tests HA-frei; E2E gegen echte HA-Instanz; Tests für Migrationen.
- Performance: keine Polling-Schleifen, on-read-Aggregate, begrenzte
  State-Attribute.
- Dokumentation: Entscheidungen (ADRs), Betrieb, Datenschutz, Upgrade-Pfade.

## 6. Ideenkatalog (Auswahl)

Bewertung: **Wert** = Nutzen für Nutzer, **Aufwand** = grobe Umsetzung,
**Risiko** = technisch/regulatorisch.

| Idee | Themenfeld | Wert | Aufwand | Risiko |
|---|---|---|---|---|
| Verlauf + Void/Restore + Audit-Log | Erfassen/Vertrauen | hoch | L | mittel (Schema, Statistik) |
| Backup-Restore inkl. Teil-Restore | Vertrauen | sehr hoch | L | mittel (Konflikte, Personen-Mapping) |
| UI-i18n de/en (HA-nativ) | Zugänglich | hoch | L | niedrig |
| Erinnerungen + Wochenbericht + Blueprints | Verstehen | hoch | M–L | niedrig |
| Onboarding mit optionalen Schritten | Zugänglich | hoch | M | niedrig |
| Rückdatieren unbegrenzt | Erfassen | hoch | M | niedrig (Zeitzonen) |
| Medikamente/Adhärenz | Erfassen | sehr hoch | L | mittel (Datenmodell) |
| Schlaf + Gewicht + Aktivität | Erfassen | hoch | L | niedrig |
| Korrelationen/Insights | Verstehen | sehr hoch | L | mittel (Statistik, Erklärbarkeit) |
| Arzt-Export (PDF) | Verstehen | hoch | M | niedrig |
| Geräte-Integrationen | Verbinden | sehr hoch | L | hoch (APIs, Auth, Cloud) |
| Sprache/NFC/Widgets | Erfassen | mittel–hoch | M | niedrig |
| Mehrbenutzer/ACL | Vertrauen | hoch | L | hoch (Architektur) |
| Anomalie-Erkennung | Verstehen | mittel | L | mittel (False Positives) |
| Optional lokale KI-Zusammenfassung | Verstehen | mittel | L | hoch (Privacy/Erwartung) |

## 7. Roadmap-Horizonte

> Die konkreten P1-Umsetzungen stehen in `docs/PLAN-UX-P1.md`. Hier nur die
> große Linie; Reihenfolge ist ein Vorschlag.

### Now — 0.14 „Vertrauen & Korrigierbarkeit"

- Verlauf + Void/Restore + Audit-Log
- Backup-Restore (Merge/Replace, Teil-Restore, Dry-Run)
- UI-i18n de/en (HA-nativ)
- Erinnerungen + Wochenbericht + Blueprints
- Onboarding mit optionalen Schritten
- Rückdatieren unbegrenzt

### Next — 0.15–0.17 „Verstehen & Verbinden"

- Verlaufsbrowser mit Filtern/Zeiträumen
- Korrelationen und personalisierte Ziele
- Arzt-Export (PDF/Markdown)
- Mehrbenutzer/ACL und dokumentierter Lösch-/Audit-Pfad
- Erste Geräte-Integration (z. B. Withings/Omron) und Sprach-/NFC-Eingabe

### Later — 1.x „Gesundheitsbild"

- Medikamente, Schlaf, Gewicht, Aktivität, Symptome/Labor, Zyklus
- Anomalie-Erkennung und optionale lokale KI-Zusammenfassungen
- Breitere Geräte-/Health-Connect-Integrationen
- Community-Blueprint- und Übersetzungsökosystem

## 8. Nicht-Ziele

- **Keine Diagnose/Therapieempfehlung** und keine Entscheidung über
  Medikation.
- **Keine Cloud-Konten** oder Sync-Dienste als Pflicht.
- **Keine Werbung, kein Datenverkauf, keine Bezahlschranke** für
  Grundfunktionen.
- **Kein Ersatz** für medizinische Geräte oder ärztliche Messungen.
- **Keine soziale Plattform** (Feeds, Likes, öffentliche Profile).
- **Kein Hard-Delete in der UI.** Löschen ist Void mit Audit; vollständige
  Entfernung nur manuell über die Store-Datei/Integration außerhalb der UI.
- **Keine ungefragte KI** über Gesundheitsdaten; KI nur opt-in und lokal
  bevorzugt.

## 9. Erfolgsmessung

- **Aktivierung:** Anteil der Installationen, die nach 7 Tagen noch erfassen.
- **Datenvollständigkeit:** Tage mit mindestens einer Buchung/Messung pro
  Woche (freiwillig, lokal auswertbar; keine Telemetrie).
- **Korrigierbarkeit:** Anteil korrigierter/gelöschter Einträge ohne
  Datenverlust; erfolgreiche Restores.
- **Qualität:** Testabdeckung der Kernlogik, E2E-Stabilität, CI-Dauer.
- **Zugänglichkeit:** Übersetzungsabdeckung de/en, A11y-Checks, mobile
  Bedienbarkeit.
- **Vertrauen:** dokumentierte Restore-Tests, keine offenen Privacy-Findings.

## 10. Risiken & Annahmen

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Scope-Creep durch viele Gesundheitsdomänen | Release verzögert sich | klare Horizonte, ein Thema pro Release |
| HA-Breaking-Changes | Integration bricht | CI gegen HA-stable, frühe Warnungen, Pinning |
| Geräte-APIs/Auth ändern sich | Integrationen brechen | Adapter kapseln, Fallback auf manuelle Eingabe |
| Medizinische Erwartungshaltung | Haftungs-/Vertrauensrisiko | Disclaimer, keine Diagnosen, Erklärbarkeit |
| Audit-Log vs. Löschpflicht | Privacy-Konflikt | bewusst kein Hard-Delete; Audit-Cap + manueller Store-Löschweg; Restrisiko dokumentiert |
| Übersetzungsaufwand | UI bleibt teilweise deutsch | HA-native Struktur, Community, Paritätstests |
| Datenwachstum (Audit/Store) | Performance/Speicher | Caps, Retention, Kompression, Monitoring |
| Mehrbenutzer-Anforderung | Architekturumbau | früh Schnittstellen definieren, ACL als eigenes Paket |

## 11. Entscheidungen & offene Punkte

- **E1 — Löschen (entschieden 2026-10-25):** **Kein Hard-Delete in der UI.**
  Löschen = Void, Wiederherstellen = Restore; das Audit-Log bleibt append-only.
  Audit-Cap: Default 1000 Ereignisse pro Person, im Admin unbegrenzt
  einstellbar. Vollständige Entfernung nur durch Löschen der Store-Datei/
  Integration außerhalb der UI. Die DSGVO-Abwägung bleibt als Restrisiko für
  eine öffentliche 1.0 dokumentiert.
- **E2 — Mehrbenutzer/ACL:** Wann und mit welchem Modell (pro HA-Nutzer eine
  Person, Rollen, gemeinsame Haushalte)?
- **E3 — Geräte-Reihenfolge:** Welche Integration zuerst (Withings, Omron,
  Apple Health/Health Connect, Garmin)?
- **E4 — KI:** Bleibt KI dauerhaft optional/lokal, oder ist eine explizit
  opt-in Cloud-Zusammenfassung denkbar?
- **E5 — Mobile:** Reicht die HA-App/PWA, oder braucht es eine eigene App?
- **E6 — Arzt-Export:** PDF direkt erzeugen oder Markdown/CSV + Druckansicht?

## 12. Wie Ideen in die Roadmap kommen

1. **Ideation** (dieses Dokument): Problem, Nutzen, Risiko, grobe Richtung.
2. **Requirements:** REQ mit Akzeptanzkriterien in `docs/REQUIREMENTS.md`.
3. **Plan:** technischer Umsetzungsplan (z. B. `docs/PLAN-UX-P1.md`) mit
   Datenmodell, Migration, Tests, Release-Schnitt.
4. **Umsetzung:** Feature-Branch, Tests, Review, E2E, Release-Dreiklang.
5. **Lernen:** Nach jedem Release prüfen, ob die Vision-Annahmen tragen;
   dieses Dokument fortschreiben.

## 13. Änderungslog

| Datum | Änderung |
|---|---|
| 2026-10-25 | Erstentwurf; Schwerpunkte Erfassen/Verstehen/Vertrauen, 2–3-Jahres-Horizont, Nicht-Ziele und offene Entscheidungen |
| 2026-10-25 | Entscheidungen: kein Hard-Delete in der UI, Audit-Cap 1000 (Admin: unbegrenzt), Karten-Verlauf Default aus, Reminder via `notify.*`, Wochenbericht nur als Notification, Release Notes de/en |

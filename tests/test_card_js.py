"""Tests: www/health-o-mat-card.js — statische Regressionen (kein JS-Runner).

Die Karte ist ein Vanilla-Web-Component ohne Build-Toolchain. Diese Tests
sichern die Eigenschaften, die bei Refactorings still kaputtgehen können, als
Text-Assertions auf die Quelldatei:

* die Karte referenziert ausschließlich die erlaubten `health_o_mat/*`-WS-
  Kommandos (keine Admin-/Settings-Kommandos),
* das `areas`-Gating (Bereiche ausblenden) ist vorhanden,
* die Map der freundlichen Blutdruck-Kategorielabels deckt alle sieben Keys ab,
* die DOM-Listener werden im `connectedCallback` registriert (nicht nur im
  Konstruktor) — Lovelace haengt die Karte beim Mounten ab und wieder an.

Absichtlich tolerant gegenüber Formatierung: es wird nur der Dateitext gelesen.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CARD_JS = os.path.join(
    _REPO_ROOT, "custom_components", "health_o_mat", "www", "health-o-mat-card.js"
)

# Erlaubte WS-Kommandos der eingebetteten Karte (nur lesend, kein Admin).
_ALLOWED_WS_COMMANDS = {
    "list_persons",
    "panel_data",
    "subscribe",
    # REQ-HOM-115: Verlauf lesen und einzelne Einträge korrigieren (kein
    # Admin-Vorgang, dieselbe API wie im Panel).
    "list_history",
    "void_entry",
    "restore_entry",
}

# Admin-/Settings-Kommandos, die NIE in der Karte auftauchen dürfen.
_FORBIDDEN_WS_COMMANDS = {
    "get_settings",
    "set_settings",
    "export_csv",
    "start_person_flow",
    "delete_person",
    "backup",
    "set_ui_settings",
    "get_ui_settings",
    "restore_backup",
    "list_import_files",
}

# Die sieben WHO-Blutdruck-Kategorien (logic.bp_category).
_BP_CATEGORY_KEYS = (
    "optimal",
    "normal",
    "high_normal",
    "grade_1",
    "grade_2",
    "grade_3",
    "crisis",
)


def _card_source() -> str:
    with open(_CARD_JS, encoding="utf-8") as handle:
        return handle.read()


def _referenced_ws_commands(text: str) -> set[str]:
    return set(re.findall(r"health_o_mat/([a-z_]+)", text))


def test_card_file_exists_and_is_vanilla():
    """Die Karte existiert und ist ein eigenständiges Web-Component-Modul."""
    text = _card_source()

    assert "class HealthOMatCard" in text
    assert "customElements.define" in text
    # Keine externen Importe / Build-Artefakte (Vanilla ES-Modul).
    assert re.search(r"^\s*import\s", text, re.M) is None
    assert "require(" not in text


def test_card_references_only_allowed_ws_commands():
    """Nur lesende WS-Kommandos, keine Admin-/Settings-Kommandos."""
    referenced = _referenced_ws_commands(_card_source())

    assert "list_persons" in referenced
    assert "panel_data" in referenced
    assert referenced.isdisjoint(_FORBIDDEN_WS_COMMANDS)
    assert referenced <= _ALLOWED_WS_COMMANDS


def test_card_areas_gating_present():
    """`areas`-Gating ist vorhanden (Trinken/Blutdruck/Wohlbefinden)."""
    text = _card_source()

    assert "areas" in text
    # Alle drei Bereiche werden einzeln ausgewertet.
    assert "areas.drink" in text
    assert "areas.bp" in text
    assert "areas.wellbeing" in text


def test_card_category_label_map_covers_all_keys():
    """Die freundliche Kategorielabel-Map deckt alle sieben Keys ab."""
    text = _card_source()

    match = re.search(r"BP_CATEGORY_LABELS\s*=\s*\{(.*?)\}", text, re.S)
    assert match is not None, "BP_CATEGORY_LABELS-Map fehlt in der Karte"

    block = match.group(1)
    for key in _BP_CATEGORY_KEYS:
        assert re.search(rf"(?<![\w]){re.escape(key)}\s*:", block), (
            f"Blutdruck-Kategorie '{key}' fehlt in BP_CATEGORY_LABELS"
        )


# --- REQ-HOM-112: Wohlbefinden-Score + Sparkline in der Karte ----------------

# Anzahl der Meldungen im kompakten Trend der Karte.
_EXPECTED_TREND_POINTS = 14


def test_card_wellbeing_score_and_sparkline_helpers_exist():
    """[REQ-HOM-112] Score-/Sparkline-Logik ist in der Karte vorhanden."""
    text = _card_source()

    assert "WELLBEING_SCALE" in text
    for name in ("wellbeingScore", "wellbeingScorePoints", "wellbeingTrendSvg"):
        assert re.search(rf"function\s+{name}\s*\(", text), f"{name}() fehlt in der Karte"


def test_card_wellbeing_scale_mirror_covers_all_state_keys():
    """[REQ-HOM-112] Die Karten-Skala spiegelt alle fünf Zustands-Keys."""
    text = _card_source()

    match = re.search(r"WELLBEING_SCALE\s*=\s*\[(.*?)\]", text, re.S)
    assert match is not None, "WELLBEING_SCALE fehlt in der Karte"

    block = match.group(1)
    for key in ("very_bad", "bad", "okay", "good", "great"):
        assert re.search(rf'\bkey\s*:\s*"{re.escape(key)}"', block), (
            f"Zustand '{key}' fehlt in der Karten-Skala"
        )


def test_card_wellbeing_trend_uses_last_14_reports():
    """[REQ-HOM-112] Der Trend nutzt die letzten 14 Meldungen (`.slice(-N)`)."""
    text = _card_source()

    match = re.search(r"WELLBEING_TREND_POINTS\s*=\s*(\d+)", text)
    assert match is not None, "WELLBEING_TREND_POINTS fehlt in der Karte"
    assert int(match.group(1)) == _EXPECTED_TREND_POINTS

    assert re.search(r"slice\(\s*-WELLBEING_TREND_POINTS\s*\)", text), (
        "Der Trend schneidet die Historie nicht auf die letzten Meldungen"
    )


def test_card_wellbeing_chart_is_accessible():
    """[REQ-HOM-112] SVG mit role="img" + aria-label, Datenpunkte mit <title>."""
    text = _card_source()

    assert 'role="img"' in text
    assert "aria-label" in text
    assert "<title>" in text


def test_card_wellbeing_chart_has_empty_state_hint():
    """[REQ-HOM-112] Leerfall: verständlicher Hinweis statt leerem Chart."""
    text = _card_source()

    assert "Noch keine Wohlbefinden-Meldung" in text


def test_card_wellbeing_score_badge_uses_scale_maximum():
    """[REQ-HOM-112] Das Score-Badge zeigt `Score / Skalenmaximum`."""
    text = _card_source()

    assert "wellbeing_score" in text  # Live-Entity als Quelle
    assert re.search(r"\$\{score\}\s*/\s*\$\{scaleMax\}", text), (
        "Das Score-Badge zeigt den Score nicht gegen das Skalenmaximum"
    )


def test_card_wellbeing_chart_needs_no_external_library():
    """[REQ-HOM-112] Keine externe Bibliothek für Score/Sparkline (Vanilla)."""
    text = _card_source()

    assert re.search(r"^\s*import\s", text, re.M) is None
    assert "require(" not in text


# --- REQ-HOM-112: Quelltext-Assertions zur Series-Logik der Karte -------------
#
# Die Historie führt vergangene Meldungen (siehe `store.set_wellbeing`): ein
# Eintrag bedeutet "dieser Status wurde zu diesem Zeitpunkt gemeldet", der
# AKTUELLE Zustand steht ausschliesslich im `wellbeing`-Block. Die Sparkline
# muss den aktuellen Wert an die Serie anhaengen — sonst endet sie am
# abgeloesten Wert und widerspricht dem Badge.


def _js_function_block(text: str, name: str) -> str:
    """Quelltext des Funktionsrumpfs von `name` (bis zur Zeile `}` auf Spalte 0)."""
    match = re.search(rf"function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", text)
    assert match is not None, f"{name}() fehlt im Quelltext"
    end = text.find("\n}", match.end())
    assert end != -1, f"{name}() hat keinen abschliessenden Block"
    return text[match.end() : end]


def test_req_hom_112_card_wellbeing_series_appends_current_value():
    """[REQ-HOM-112] Die Karte haengt den aktuellen Wert an die Sparkline-Serie.

    Die Karte bleibt eigenstaendig (kein `import` aus dem Panel-Modul) und hat
    darum ihre eigene Series-Logik.
    """
    text = _card_source()

    # Eigenstaendig: die Karte importiert nichts (kein Panel-Modul).
    assert re.search(r"^\s*import\s", text, re.M) is None, (
        "die Karte importiert fremde Module (sie muss eigenstaendig bleiben)"
    )
    assert re.search(r"function\s+wellbeingSeries\s*\(\s*history\s*,\s*current\s*\)", text), (
        "die Karte hat keine eigene Series-Logik"
    )
    body = _js_function_block(text, "wellbeingSeries")

    # Die Serie startet mit der Historie …
    assert "wellbeingScorePoints(history)" in body, "die Serie startet nicht mit der Historie"
    # … und haengt den aktuellen Wert an.
    push = re.search(r"points\.push\(\s*\{(?P<fields>.*?)\}\s*\)\s*;", body, re.S)
    assert push is not None, "der aktuelle Wert wird nicht an die Serie angehaengt"
    assert re.search(r"\bscore\b", push.group("fields")), (
        "der angehaengte Punkt traegt keinen Score"
    )
    # Ohne verwertbaren aktuellen Score bleibt die Serie = Historie.
    assert re.search(r"if\s*\(\s*score\s*={2,3}\s*null\s*\)\s*return\s+points\s*;", body), (
        "ohne aktuellen Score muss die Serie der Historie entsprechen"
    )

    # Aufrufstelle: Serie = Historie + aktueller Wert, danach auf 14 gekuerzt.
    assert re.search(
        r"wellbeingSeries\(\s*wb\.history\s*,\s*current\s*\)\s*"
        r"\.slice\(\s*-WELLBEING_TREND_POINTS\s*\)",
        text,
    ), "die Sparkline nutzt nicht die Serie inklusive aktuellem Wert"


def test_req_hom_112_card_badge_and_sparkline_share_resolved_score():
    """[REQ-HOM-112] Badge und Sparkline nutzen denselben aufgeloesten Score.

    Quelle des Scores: Live-Entity, sonst Server-Feld, sonst aus dem Key
    abgeleitet. Badge und Sparkline duerfen nicht unterschiedliche Werte
    anzeigen.
    """
    text = _card_source()

    assert re.search(r"const\s+score\s*=", text), "der aufgeloeste Score fehlt"
    assert re.search(r":\s*wellbeingScore\(\s*wb\s*\)", text), (
        "der Score wird nicht fallbackweise aus dem Zustands-Key abgeleitet"
    )
    # Derselbe aufgeloeste Score wandert in die Serie (Sparkline) …
    assert re.search(r"current\s*=\s*\{[^}]*score\s*:\s*score", text, re.S), (
        "die Serie bekommt nicht den aufgeloesten Score"
    )
    # … und ins Badge.
    assert re.search(
        r'<span class="score">\$\{score\}\s*/\s*\$\{scaleMax\}</span>',
        text,
    ), "das Score-Badge nutzt nicht den aufgeloesten Score"


# --- REQ-HOM-011/014: konfigurierbare Karte (docs/PLAN-CARD-CONFIG.md) ------
#
# Die Karte bleibt ein eigenstaendiges Vanilla-Web-Component. Diese Tests
# sichern die Bindung des Konfigurationsschemas (9 Schalter, Getraenke-Filter,
# Legacy-Override, Eingabe-Aktionen) als Quelltext-Assertions.

# Die neun Schalter des verbindlichen Schemas (je einmal, keine Duplikate).
_CARD_SHOW_KEYS = (
    "show_person",
    "show_hydration",
    "show_blood_pressure",
    "show_blood_pressure_history",
    "show_wellbeing",
    "show_drinks",
    "show_manual_amounts",
    "show_blood_pressure_input",
    "show_wellbeing_input",
    "show_wellbeing_numeric",
    "show_undo",
)


def _js_class_block(text: str, name: str) -> str:
    """Quelltext einer Klasse (bis zur Zeile `}` auf Spalte 0)."""
    match = re.search(rf"class\s+{re.escape(name)}\s+extends\s+HTMLElement\s*\{{", text)
    assert match is not None, f"Klasse {name} fehlt im Quelltext"
    end = text.find("\n}", match.end())
    assert end != -1, f"Klasse {name} hat keinen abschliessenden Block"
    return text[match.end() : end]


def _js_method_block(text: str, name: str) -> str:
    """Quelltext einer Klassenmethode (bis zur naechsten Methode auf Klassenebene).

    Die Methode endet an der ersten Zeile `  }` (zwei Leerzeichen) — die
    Klassenmethoden der Karte sind so eingerueckt.
    """
    match = re.search(rf"\n  (?:async\s+)?{re.escape(name)}\s*\([^)]*\)\s*\{{", text)
    assert match is not None, f"Methode {name}() fehlt im Quelltext"
    end = text.find("\n  }\n", match.end())
    assert end != -1, f"Methode {name}() hat kein Ende"
    return text[match.end() : end]


def test_card_show_flag_list_covers_exactly_the_nine_schema_keys():
    """[Card-Config] `CARD_SHOW_KEYS` enthaelt genau die Schema-Schalter."""
    text = _card_source()
    match = re.search(r"CARD_SHOW_KEYS\s*=\s*\[(.*?)\]", text, re.S)
    assert match is not None, "CARD_SHOW_KEYS fehlt in der Karte"

    keys = re.findall(r'"([a-z_]+)"', match.group(1))
    assert keys == list(_CARD_SHOW_KEYS), f"Schema-Schalter weichen ab: {keys}"
    assert len(keys) == len(set(keys)) == 11


def test_card_body_gates_every_block_with_its_flag_and_the_area():
    """[Card-Config] Jeder Block ist ein AND aus Integrations-Bereich und Flag."""
    body = _js_method_block(_card_source(), "_body")

    expected = {
        "show_hydration": "areas.drink && flags.show_hydration",
        "show_blood_pressure": "areas.bp && flags.show_blood_pressure",
        "show_blood_pressure_history": "areas.bp && flags.show_blood_pressure_history",
        "show_wellbeing": "areas.wellbeing && flags.show_wellbeing",
        "show_drinks": "areas.drink && flags.show_drinks",
        "show_manual_amounts": "areas.drink && flags.show_manual_amounts",
        "show_blood_pressure_input": "areas.bp && flags.show_blood_pressure_input",
        "show_wellbeing_input": "areas.wellbeing && flags.show_wellbeing_input",
        "show_undo": "areas.drink && flags.show_undo",
    }
    for key, expression in expected.items():
        assert expression in body, f"Block '{key}' ist nicht an Bereich+Flag gebunden"

    # `getCardSize()` leitet die Hoehe aus den aktiven Bloecken ab (kein fixes
    # 5 mehr) und behaelt ein sinnvolles Minimum.
    size = _js_method_block(_card_source(), "getCardSize")
    assert "this._flags()" in size, "getCardSize ignoriert die Karten-Konfiguration"
    assert "flags.show_hydration" in size and "flags.show_undo" in size
    assert re.search(r"return\s+Math\.max\(\s*1\s*,", size), "getCardSize hat kein Minimum"


def test_card_config_defaults_and_backward_compatibility():
    """[Card-Config] Defaults: Anzeige unverändert, Eingaben bewusst AN.

    Zwei getrennte Fakten, die nicht verwechselt werden dürfen:

    * Die VORHANDENEN Anzeige-Blöcke behalten ihre bisherigen Defaults (`true`)
      — ein Bestands-Dashboard ohne die neuen Keys rendert unverändert.
    * Die EINGABE-Blöcke sind eine neue Funktion und bewusst per Default `true`
      (Schema: „Eingaben an“). Das ist KEINE Rückwärtskompatibilität im
      engeren Sinn, sondern eine dokumentierte Erweiterung.
    """
    text = _card_source()
    display_keys = (
        "show_person",
        "show_hydration",
        "show_blood_pressure",
        "show_wellbeing",
    )
    input_keys = (
        "show_drinks",
        "show_manual_amounts",
        "show_blood_pressure_input",
        "show_wellbeing_input",
        "show_undo",
    )

    # Gemeinsamer Default-Ausdruck fuer ALLE neun Schalter: alles, was ein
    # Bestands-Config nicht nennt, faellt auf `true` zurueck.
    assert re.search(r"flags\[key\]\s*=\s*toBool\(\s*source\[key\]\s*,\s*true\s*\)", text), (
        "die show_*-Defaults sind nicht `true`"
    )
    # Beide Gruppen liegen im selben Schema (sonst greift der Default nicht).
    listed = re.search(r"CARD_SHOW_KEYS\s*=\s*\[(.*?)\]", text, re.S)
    assert listed is not None, "CARD_SHOW_KEYS fehlt in der Karte"
    for key in display_keys + input_keys:
        assert f'"{key}"' in listed.group(1), f"{key} fehlt im Schema"

    # Ein Bestands-Config (ohne die neuen Keys) rendert weiter: der
    # Normalisierer verträgt fehlende/fremde Quellen und die Blöcke lesen nur
    # die normalisierten Flags — nie die Rohkeys.
    assert re.search(
        r'source\s*=\s*raw\s*&&\s*typeof\s+raw\s*===\s*"object"\s*\?\s*raw\s*:\s*\{\}', text
    ), "normalizeCardConfig vertraegt keine fehlende/ungueltige Konfiguration"
    body = _js_method_block(text, "_body")
    assert "this._config.show_" not in body, (
        "ein Block liest Roh-Keys statt der normalisierten Flags (fehlende Keys wuerden crashen)"
    )

    # Getraenke: keine Auswahl = alle.
    assert re.search(r"function\s+normalizeDrinkKeys", text)
    assert re.search(r"if\s*\(\s*!Array\.isArray\(\s*value\s*\)\s*\)\s*return\s*\[\]", text)
    # Manuelle Mengen: Default [200, 500], freies Feld an.
    assert re.search(r"DEFAULT_MANUAL_AMOUNTS\s*=\s*\[\s*200\s*,\s*500\s*\]", text)
    assert re.search(
        r"return\s+amounts\.length\s*\?\s*amounts\s*:\s*DEFAULT_MANUAL_AMOUNTS\.slice\(\)", text
    ), "eine leere Mengenliste faellt nicht auf den Default zurueck"
    assert re.search(
        r"allowCustomAmount:\s*toBool\(\s*source\.allow_custom_amount\s*,\s*true\s*\)", text
    )
    # Der Legacy-Override wird weiterhin akzeptiert.
    assert re.search(
        r"quickDrinks:\s*normalizeLegacyQuickDrinks\(\s*source\.quick_drinks\s*\)", text
    )


def test_card_explicit_bp_input_flag_overrides_display_flag():
    """[Card-Config] Explizites `show_blood_pressure_input` schlaegt die Anzeige."""
    text = _card_source()
    normalizer = _js_function_block(text, "normalizeCardConfig")

    # Die Explizitheit der Rohkeys bleibt erhalten …
    assert re.search(
        r"explicit\s*=\s*new\s+Set\(\s*Object\.keys\(\s*source\s*\)\s*\)", normalizer
    ), "die explizit gesetzten Keys werden nicht gemerkt"
    # … und nur ohne expliziten Wert folgt die Eingabe der Anzeige.
    assert re.search(
        r"if\s*\(\s*!explicit\.has\(\s*\"show_blood_pressure_input\"\s*\)\s*\)\s*"
        r"\{\s*flags\.show_blood_pressure_input\s*=\s*flags\.show_blood_pressure\s*;",
        normalizer,
        re.S,
    ), "die BD-Eingabe folgt dem Anzeige-Schalter nicht bzw. uebersteuert ihn nicht korrekt"


def test_card_head_respects_show_person():
    """[Card-Config] `show_person: false` unterdrueckt das Personen-Dropdown."""
    head = _js_method_block(_card_source(), "_head")

    assert "flags.show_person" in head, "der Kopf ignoriert show_person"
    # Personenwechsel: die gecachte Liste bleibt erhalten (sonst verschwindet
    # das Dropdown beim Reload und es braucht einen zweiten Roundtrip).
    change = _js_method_block(_card_source(), "_onSelectChange")
    assert "this._persons = null" not in change, (
        "der Personenwechsel verwirft die gecachte Personenliste"
    )
    assert "this._loadData()" in change, "der Personenwechsel laedt keine Daten"
    loader = _js_method_block(_card_source(), "_loadData")
    assert "filterPersons(persons, cfg.personFilter)" in loader, (
        "der Personen-Filter wird beim Laden nicht angewendet"
    )
    fallback = (
        r"entryId\s*=\s*known\s*\?\s*entryId\s*:\s*preferred\s*\?"
        r"\s*preferred\.entry_id\s*:\s*allowed\[0\]\.entry_id"
    )
    assert re.search(fallback, loader), (
        "ohne Auswahl wird nicht die erste erlaubte Person verwendet"
    )


def test_card_person_switch_resets_person_scoped_state():
    """[F3] Personenwechsel verwirft Entwurf und Fehler der alten Person.

    Sonst wird ein fuer Person A getippter BD-Entwurf unter Person B gerendert
    und kann dort gespeichert werden (Datenintegritaet). Der Wechsel darf nur
    bei einer ECHTEN Aenderung aufraeumen — dieselbe Person erneut zu waehlen
    ist kein Wechsel. Das Verhalten sichert der Node-Test weiter unten.
    """
    change = _js_method_block(_card_source(), "_onSelectChange")

    guard = re.search(r"if\s*\(\s*nextEntry\s*!==\s*this\._activeEntry\s*\)\s*\{", change)
    assert guard is not None, (
        "der Personenwechsel prueft nicht, ob sich die Person tatsaechlich aendert"
    )
    clear_block = change[guard.end() :]
    for statement in (
        "this._bpDraft = null",
        'this._amountDraft = ""',
        'this._bpError = ""',
        'this._amountError = ""',
        'this._wbError = ""',
        'this._actionError = ""',
        "this._activeEntry = nextEntry",
    ):
        assert statement in clear_block, f"der Personenwechsel raeumt {statement!r} nicht auf"
    # Nichts davon darf VOR der Wechsel-Pruefung stehen (sonst loescht schon
    # das Neu-Auswaehlen derselben Person den Entwurf).
    before_guard = change[: guard.start()]
    for statement in ("this._bpDraft = null", 'this._amountDraft = ""'):
        assert statement not in before_guard, (
            f"{statement!r} steht vor der Wechsel-Pruefung und loescht auch ohne Wechsel"
        )


def test_card_action_error_clears_on_successful_reload():
    """[F6] Ein erfolgreicher stiller Reload beendet den Aktions-Fehlerzustand."""
    loader = _js_method_block(_card_source(), "_loadData")

    clear = re.search(
        r'if\s*\(\s*silent\s*&&\s*this\._data\s*\)\s*this\._actionError\s*=\s*""\s*;',
        loader,
    )
    assert clear is not None, "ein erfolgreicher Reload loescht die alte Aktions-Meldung nicht"
    assert loader.find("this._data = data") < clear.start(), (
        "die Aktions-Meldung wird vor dem erfolgreichen Daten-Update geloescht"
    )


def test_card_drinks_filter_by_key_and_never_empty():
    """[Card-Config] `drinks` filtert die Integrationsliste; leere Auswahl = alle."""
    drinks = _js_method_block(_card_source(), "_quickDrinks")

    assert "this._data" in drinks and "quick_drinks" in drinks, (
        "die Integrations-Getraenke (panel_data.quick_drinks) werden nicht verwendet"
    )
    assert re.search(
        r"normalizeServerQuickDrinks\(\s*this\._data\s*&&\s*this\._data\.quick_drinks\s*\)", drinks
    ), "_quickDrinks liest panel_data.quick_drinks nicht"
    assert re.search(r"cfg\.drinks\.includes\(\s*drink\.key\s*\)", drinks), (
        "die Getraenke werden nicht nach Key gefiltert"
    )
    assert re.search(r"filtered\.length\s*\?\s*filtered\s*:\s*list", drinks), (
        "eine leere Schnittmenge faellt nicht auf 'alle' zurueck"
    )
    assert re.search(r"if\s*\(\s*!cfg\.drinks\.length\s*\)\s*return\s+list", drinks)


def test_card_legacy_quick_drinks_override_wins_over_drinks_filter():
    """[Card-Config] Der Legacy-Override `quick_drinks` gewinnt immer."""
    drinks = _js_method_block(_card_source(), "_quickDrinks")

    override = drinks.find("cfg.quickDrinks.length")
    server = drinks.find("quick_drinks")
    assert override != -1, "der Legacy-Override wird nicht ausgewertet"
    assert server == -1 or override < server, (
        "der Legacy-Override wird nicht VOR der Integrationsliste ausgewertet"
    )
    assert re.search(r"return\s+cfg\.quickDrinks\s*;", drinks)


def test_card_drink_booking_sends_the_label_as_drink_type():
    """[Card-Config] Buchung sendet `drink_type` = Label (Bugfix statt 'Eigen')."""
    text = _card_source()
    book = _js_method_block(text, "_book")

    assert re.search(r"async\s+_book\(\s*ml\s*,\s*drinkType\s*\)", text), (
        "_book nimmt keinen Getraenketyp entgegen"
    )
    assert re.search(
        r'drink_type:\s*drinkType\s*\?\s*String\(\s*drinkType\s*\)\s*:\s*"Eigen"', book
    ), "die Buchung sendet kein drink_type"
    # Quell-Button: das Label des Getraenks wandert in das Attribut.
    actions = _js_method_block(text, "_drinkActions")
    assert re.search(r'data-drink-type="\$\{\s*escapeHtml\(\s*drink\.label\s*\)\s*\}"', actions), (
        "der Getraenke-Button traegt nicht das Label als drink_type"
    )
    # Manuelle Mengen senden explizit "Eigen".
    amounts = _js_method_block(text, "_manualAmounts")
    assert 'data-drink-type="Eigen"' in amounts
    # Der Klick-Handler reicht den Typ an _book weiter.
    click = _js_method_block(text, "_onCardClick")
    assert "data-drink-type" in click and re.search(
        r"target\.getAttribute\(\s*\"data-drink-type\"\s*\)", click
    )

    # Aktionsfehler bleiben sichtbar, auch wenn Daten geladen sind: eigener
    # Banner-Kanal (`_actionError`), NICHT `_error` (das ist fuer Ladefehler
    # reserviert und wird bei vorhandenen Daten nicht gerendert).
    for method in ("_book", "_undo"):
        body = _js_method_block(text, method)
        assert "this._actionError = (err && err.message)" in body, (
            f"{method} meldet Aktionsfehler nicht im Banner-Kanal"
        )
        assert "this._error =" not in body, f"{method} ueberschreibt den Ladefehler-Kanal"
        assert 'this._actionError = ""' in body, (
            f"{method} raeumt die alte Aktions-Meldung nicht beim neuen Versuch"
        )
    banner = _js_method_block(text, "_actionBanner")
    assert 'class="banner"' in banner and 'role="alert"' in banner
    assert "_actionBanner()" in _js_method_block(text, "_html"), (
        "die Karte rendert den Aktions-Banner nicht"
    )
    # Fortschrittsmeldung der Schnellbuchung ist fuer Screenreader hoerbar.
    assert 'role="status" aria-live="polite"' in _js_method_block(text, "_drinkActions")


def test_card_manual_amounts_presets_custom_field_and_bounds():
    """[Card-Config] Preset-Buttons, freies Feld und Bereichsvalidierung 1…10000."""
    text = _card_source()
    amounts = _js_method_block(text, "_manualAmounts")
    submit = _js_method_block(text, "_submitCustomAmount")

    assert "cfg.manualAmounts" in amounts, "die Presets kommen nicht aus der Konfiguration"
    assert "cfg.allowCustomAmount" in amounts, "das freie Zahlenfeld ignoriert allow_custom_amount"
    assert 'data-role="custom-amount"' in amounts, "das freie Zahlenfeld fehlt"
    assert 'data-action="book-custom"' in amounts, "der Buchen-Button fuers freie Feld fehlt"
    assert 'role="alert"' in amounts, "Validierungsfehler werden nicht inline angezeigt"
    # F7: eigene Live-Region fuer manuelle Buchungen, wenn der Getraenke-Block
    # (show_drinks: false) keine Statuszeile rendert.
    assert 'role="status" aria-live="polite"' in amounts, (
        "manuelle Buchungen haben ohne Getraenke-Block keine Hoer-Meldung"
    )
    # F4: getippte eigene Menge wird wieder eingesetzt und ueberlebt Fehler.
    assert 'value="${escapeHtml(this._amountDraft || "")}"' in amounts, (
        "der Mengen-Entwurf wird nicht wieder eingesetzt"
    )
    assert "this._amountDraft = raw" in submit, (
        "der fehlgeschlagene Submit verwirft den getippten Wert"
    )
    assert re.search(
        r'if\s*\(\s*!this\._actionError\s*\)\s*\{[^}]*this\._amountDraft\s*=\s*""',
        submit,
        re.S,
    ), "der Entwurf wird nicht nur nach Erfolg geleert"

    assert re.search(r"MAX_AMOUNT_ML\s*=\s*10000", text)
    assert re.search(r"MIN_AMOUNT_ML\s*=\s*1\b", text)
    assert re.search(r"\^\\d\+\$", submit), "die Eingabe wird nicht als Ganzzahl validiert"
    assert re.search(r"value\s*<=\s*MAX_AMOUNT_ML", submit), "die Obergrenze wird nicht geprueft"
    # Kein geworfener Fehler: der Fehler landet im Render-Zustand.
    assert "_amountError" in submit
    assert not re.search(r"throw\s+new\s+Error", submit)


def test_card_bp_input_uses_service_with_note_and_bounds():
    """[Card-Config] BD-Eingabe: Service, Notizfeld (eingeklappt), Grenzen."""
    text = _card_source()
    form = _js_method_block(text, "_bloodPressureInput")
    save = _js_method_block(text, "_saveBp")

    assert 'data-role="bp-sys"' in form
    assert 'data-role="bp-dia"' in form
    assert 'data-role="bp-pulse"' in form
    assert 'data-action="save-bp"' in form
    assert '<details class="note"' in form, "das Notizfeld ist nicht einklappbar"
    assert 'data-role="bp-note"' in form
    assert "open" not in re.search(r"<details[^>]*>", form).group(0), (
        "das Notizfeld ist nicht standardmaessig zugeklappt"
    )

    # Entwurf: getippte Werte + offene Notiz ueberleben einen Re-Render
    # (Schnellbuchung, Validierungsmeldung), werden aber nach Erfolg geleert.
    assert "this._bpDraft" in form
    for role in ("sys", "dia", "pulse"):
        assert f'value="${{escapeHtml(draft.{role})}}"' in form, (
            f"der BD-Entwurf setzt {role} nicht wieder ein"
        )
    assert "${escapeHtml(draft.note)}</textarea>" in form
    assert "${noteOpen}" in form, "die Notiz wird bei vorhandenem Entwurf nicht aufgeklappt"
    assert 'this._bpDraft = { sys: "", dia: "", pulse: "", note: "" }' in save, (
        "der Entwurf wird nach erfolgreichem Speichern nicht geleert"
    )
    # Eingaben landen ohne Re-Render im Entwurf (input-Listener).
    listener = _js_method_block(text, "_onCardInput")
    assert 'role.startsWith("bp-")' in listener and "this._bpDraft" in listener
    for role in ("bp-sys", "bp-dia", "bp-pulse", "bp-note"):
        assert f'role === "{role}"' in listener, f"{role} wird nicht in den Entwurf uebernommen"

    assert '"add_blood_pressure"' in save
    for field in ("systolic", "diastolic", "pulse", "note"):
        assert re.search(rf"\b{field}\b", save), f"das Feld {field} wird nicht gesendet"
    assert re.search(r"BP_SYS_MIN\s*=\s*40", text)
    assert re.search(r"BP_SYS_MAX\s*=\s*260", text)
    assert re.search(r"BP_DIA_MIN\s*=\s*40", text)
    assert re.search(r"BP_DIA_MAX\s*=\s*260", text)
    assert re.search(r"PULSE_MIN\s*=\s*20", text)
    assert re.search(r"PULSE_MAX\s*=\s*250", text)
    assert "_bpError" in save and 'role="alert"' in form
    # Pflichtfelder ohne Puls: Puls ist optional.
    assert re.search(r'pulseRaw\s*===\s*""\s*\?\s*null', save)
    # Daten werden nach dem Speichern neu geladen.
    assert "_loadData(true)" in save


def test_card_wellbeing_input_service_scale_and_active_state():
    """[Card-Config] Wohlbefinden: Service, 5 Buttons, aktiver Zustand, Skala."""
    text = _card_source()
    form = _js_method_block(text, "_wellbeingInput")
    report = _js_method_block(text, "_reportWellbeing")
    scale = _js_method_block(text, "_wellbeingScale")

    assert '"set_wellbeing"' in report, "der Wohlbefinden-Service wird nicht aufgerufen"
    assert re.search(r"status:\s*status", report), "der Status wird nicht als `status` gesendet"
    assert re.search(r"person:\s*this\._servicePerson\(\)", report), (
        "die Person wird nicht mitgesendet"
    )
    assert "_loadData(true)" in report
    assert "this._wellbeingScale()" in form
    assert 'data-action="wellbeing"' in form
    assert 'aria-pressed="${state.key === active ? "true" : "false"}"' in form, (
        "der aktive Zustand wird nicht zugaenglich markiert"
    )
    assert 'wb-btn${state.key === active ? " active" : ""}' in form, (
        "der aktive Button wird nicht als `active` markiert"
    )
    # Fortschrittsmeldung ist fuer Screenreader hoerbar (role=status).
    assert 'role="status" aria-live="polite"' in form
    # Server-Skala wird defensiv akzeptiert, sonst der gepinnte Mirror.
    assert "wellbeing_scale" in scale
    assert "WELLBEING_SCALE" in scale
    # Exakt die zehn Zustaende in kanonischer Reihenfolge, jeder mit einem
    # expliziten Emoji (keine Tautologie: Key ODER Emoji reicht NICHT).
    scale_block = re.search(r"WELLBEING_SCALE\s*=\s*\[(.*?)\]", text, re.S)
    assert scale_block is not None, "WELLBEING_SCALE fehlt in der Karte"
    entries = re.findall(
        r'\{\s*key:\s*"([a-z_]+)",\s*label:\s*"[^"]+",\s*emoji:\s*"(\\u\{[0-9A-Fa-f]+\})"\s*\}',
        scale_block.group(1),
    )
    assert [key for key, _emoji in entries] == [
        "very_bad",
        "awful",
        "bad",
        "poor",
        "okay",
        "mixed",
        "good",
        "very_good",
        "great",
        "excellent",
    ], f"die Skala-Reihenfolge weicht ab: {entries}"
    assert len(entries) == 10 and all(emoji for _key, emoji in entries), (
        "nicht jeder Zustand hat ein explizites Emoji"
    )


def test_card_all_blocks_off_renders_readable_hint():
    """[Card-Config] Alle Bloecke aus -> verstaendlicher Hinweis statt leerer Karte."""
    body = _js_method_block(_card_source(), "_body")

    assert "Keine Blöcke aktiviert" in body
    assert "Karten-Konfiguration prüfen" in body


def test_card_schedule_render_protects_typed_inputs():
    """[Card-Config] `hass`-Updates clobbern keine fokussierten Eingabefelder."""
    schedule = _js_method_block(_card_source(), "_scheduleRender")

    assert 'active.tagName === "SELECT"' in schedule
    assert 'active.tagName === "INPUT"' in schedule
    assert 'active.tagName === "TEXTAREA"' in schedule


def test_card_reads_submitted_values_from_shadow_root():
    """[Card-Config] Werte werden beim Absenden aus dem Shadow-DOM gelesen."""
    text = _card_source()
    reader = _js_method_block(text, "_readInput")

    assert 'querySelector(`[data-role="${role}"]`)' in reader
    assert "shadowRoot" in reader


def test_card_editor_renders_all_nine_flags_in_two_groups():
    """[Card-Editor] Zwei Checkbox-Gruppen mit genau den neun Schema-Schaltern."""
    editor = _js_class_block(_card_source(), "HealthOMatCardEditor")
    display = _js_method_block(editor, "_displaySection")
    inputs = _js_method_block(editor, "_inputSection")

    assert "Anzeige" in display
    assert "Eingabe &amp; Aktionen" in inputs or "Eingabe & Aktionen" in inputs
    for key in (
        "show_person",
        "show_hydration",
        "show_blood_pressure",
        "show_blood_pressure_history",
        "show_wellbeing",
    ):
        assert f'_checkbox("{key}"' in display, f"Anzeige-Schalter {key} fehlt im Editor"
    for key in (
        "show_drinks",
        "show_manual_amounts",
        "show_blood_pressure_input",
        "show_wellbeing_input",
        "show_wellbeing_numeric",
        "show_undo",
    ):
        assert f'_checkbox("{key}"' in inputs, f"Eingabe-Schalter {key} fehlt im Editor"
    # Elf Aufrufe (plus die Methodendefinition selbst) — keine Duplikate.
    assert editor.count("_checkbox(") == 12
    assert len(re.findall(r'this\._checkbox\("show_', editor)) == 11


def test_card_editor_loads_drinks_and_renders_selection_and_amounts():
    """[Card-Editor] Getraenke-Mehrfachauswahl + Mengenliste + freies Feld."""
    text = _card_source()
    editor = _js_class_block(text, "HealthOMatCardEditor")
    drinks_section = _js_method_block(editor, "_drinksSection")
    amounts_section = _js_method_block(editor, "_amountsSection")

    # Getraenke kommen aus der Integrationsliste (read-only panel_data).
    assert '"health_o_mat/panel_data"' in editor
    assert "quick_drinks" in editor
    assert "Person wählen, um Getränke zu laden" in drinks_section
    assert "Alle Getränke" in drinks_section
    assert 'data-role="drink"' in drinks_section
    assert 'data-role="drinks-all"' in drinks_section

    # Mengen: Add/Remove + Toggle.
    assert 'data-role="amount-add"' in amounts_section
    assert 'data-role="amount-remove"' in amounts_section
    assert 'data-role="amount"' in amounts_section
    assert 'data-key="allow_custom_amount"' in amounts_section


def test_card_editor_dispatches_full_config_with_real_booleans():
    """[Card-Editor] Jede Aenderung feuert `config-changed` mit dem vollen Config."""
    editor = _js_class_block(_card_source(), "HealthOMatCardEditor")
    emit = _js_method_block(editor, "_setConfig")
    toggle = _js_method_block(editor, "_toggleFlag")

    assert 'new CustomEvent("config-changed"' in emit
    assert re.search(r"detail:\s*\{\s*config:\s*next\s*\}", emit)
    assert "bubbles: true" in emit and "composed: true" in emit

    # Checkboxen senden echte Booleans (kein "on"-String).
    handler = _js_method_block(editor, "_onValueChange")
    assert "target.checked === true" in handler
    # Freitext/Selects erst bei `change`: ein `input`-Event je Tastendruck
    # wuerde `config-changed` feuern und `setConfig()` das Feld leeren.
    assert re.search(
        r'if\s*\(\s*ev\.type\s*!==\s*"change"\s*\)\s*return;\s*\n\s*const\s+next\s*=',
        handler,
    ), "der Freitext-Editor feuert weiter bei jedem Tastendruck"
    assert re.search(r"next\[key\]\s*=\s*false", toggle), (
        "abgewaehlte Schalter werden nicht als false gespeichert"
    )
    # `entry_id`/`person` werden nie gedroppt: jede Aenderung baut auf einer
    # Kopie der bestehenden Konfiguration auf (und sendet sie vollstaendig).
    for method in ("_toggleFlag", "_toggleDrink", "_setAmountFromInput", "_onValueChange"):
        assert "Object.assign({}, this._config" in _js_method_block(editor, method), (
            f"{method}() baut nicht auf einer Kopie der bestehenden Konfiguration auf"
        )
    assert re.search(r"this\._setConfig\(\s*next\s*,\s*true\s*\)", toggle)


# --- Listener-Lifecycle (E2E-belegter Defekt: Detach beim Mounten) ---------------


def test_card_get_config_element_is_static():
    """HA's Lovelace API sucht `getConfigElement` auf der Klasse (static).

    Eine reine Instanzmethode laesst den Dashboard-Editor "visueller Editor
    wird nicht unterstuetzt" melden und faellt auf YAML zurueck.
    """
    text = _card_source()
    assert re.search(r"static\s+getConfigElement\s*\(\s*\)\s*\{", text), (
        "getConfigElement muss static sein — sonst meldet HA den visuellen "
        "Editor als nicht unterstuetzt"
    )
    # Keine (schweigend wieder eingefuehrte) Instanzmethode daneben.
    assert not re.search(r"(?<!static\s)\bgetConfigElement\s*\(\s*\)\s*\{", text)
    # Das Editor-Element muss registriert sein, sonst liefert die Methode
    # ein unbekanntes Custom Element.
    assert re.search(r"customElements\.define\(\s*EDITOR_TAG\s*,", text)


def test_card_registers_dom_listeners_in_connected_callback():
    """[Listener-Lifecycle] Karte registriert Klick/Input/Change im connectedCallback.

    Lovelace detacht die Karte beim Mounten einer Ansicht und haengt sie wieder
    an. Listener, die nur im Konstruktor registriert werden, sind danach fuer
    immer weg — Klicks tun still nichts mehr, waehrend Render-Tests gruen
    bleiben. Dieser Test sichert nur die Struktur; den Beweis, dass Klicks nach
    einem echten Detach/Attach wieder schreiben, liefert die Playwright-E2E-Suite.
    """
    text = _card_source()
    card = _js_class_block(text, "HealthOMatCard")
    connected = _js_method_block(card, "connectedCallback")
    disconnected = _js_method_block(card, "disconnectedCallback")
    constructor = _js_method_block(card, "constructor")

    # Listener wandern in den Lifecycle-Callback, nicht mehr in den Konstruktor.
    assert re.search(r'addEventListener\(\s*"click"', connected), (
        "click-Listener wird nicht im connectedCallback registriert"
    )
    assert re.search(r'addEventListener\(\s*"change"', connected), (
        "change-Listener wird nicht im connectedCallback registriert"
    )
    assert re.search(r'addEventListener\(\s*"input"', connected), (
        "input-Listener (BD-Entwurf) wird nicht im connectedCallback registriert"
    )
    assert "addEventListener" not in constructor, (
        "Konstruktor registriert weiterhin Listener (nach Detach verloren)"
    )

    # Abmelden bleibt symmetrisch; das Guard-Flag macht das Anhaengen idempotent.
    assert re.search(r'removeEventListener\(\s*"click"', disconnected)
    assert re.search(r'removeEventListener\(\s*"change"', disconnected)
    assert re.search(r'removeEventListener\(\s*"input"', disconnected)
    assert "this._listenersAttached" in connected, (
        "connectedCallback ist nicht idempotent (fehlendes Guard-Flag)"
    )
    assert "this._listenersAttached" in disconnected, (
        "disconnectedCallback setzt das Guard-Flag nicht zurueck"
    )


def test_card_editor_registers_dom_listeners_in_connected_callback():
    """[Listener-Lifecycle] Editor nutzt dasselbe symmetrische Muster."""
    text = _card_source()
    editor = _js_class_block(text, "HealthOMatCardEditor")
    connected = _js_method_block(editor, "connectedCallback")
    disconnected = _js_method_block(editor, "disconnectedCallback")
    constructor = _js_method_block(editor, "constructor")

    for event in ("input", "change", "click"):
        assert re.search(rf'addEventListener\(\s*"{event}"', connected), (
            f"{event}-Listener fehlt im connectedCallback des Editors"
        )
        assert re.search(rf'removeEventListener\(\s*"{event}"', disconnected), (
            f"{event}-Listener wird im disconnectedCallback nicht entfernt"
        )
    assert "addEventListener" not in constructor
    assert "this._listenersAttached" in connected
    assert "this._listenersAttached" in disconnected


# --- F3: Personenwechsel und personenbezogener Entwurf ------------------------
#
# Der statische Pin sichert die Struktur; der folgende Node-Test beweist das
# VERHALTEN: ein Entwurf von Person A darf einen Wechsel zu Person B nicht
# ueberleben (sonst wird er unter B gespeichert). Er nutzt denselben
# DOM-Stub-Ansatz wie die Node-Render-Tests in `tests/test_panel_js.py`
# (`vm`-Context + FakeShadowRoot/HTMLElement) — keine produktspezifischen
# Stubs, nur das Minimum, das die Karte zum Instanziieren braucht.

_NODE_CARD_PERSON_SWITCH_RUNNER = """import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; }
  addEventListener() {}
  removeEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  appendChild(child) { return child; }
}

class FakeHTMLElement {
  constructor() { this._shadow = null; }
  attachShadow() { this._shadow = new FakeShadowRoot(); return this._shadow; }
  get shadowRoot() { return this._shadow; }
  dispatchEvent() { return true; }
  setAttribute() {}
  removeAttribute() {}
}

const context = {
  HTMLElement: FakeHTMLElement,
  CustomEvent: class {
    constructor(type, init) {
      this.type = type;
      this.detail = init && init.detail ? init.detail : null;
    }
  },
  customElements: { get: () => undefined, define: () => {} },
  window: {},
  document: { createElement: () => ({}), addEventListener: () => {} },
  console: { info: () => {}, log: () => {}, warn: () => {}, error: () => {} },
  setTimeout: () => 0,
  clearTimeout: () => {},
  __out: null,
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "health-o-mat-card.js" });

vm.runInContext(
  `
  function makeCard(activeEntry) {
    const card = new HealthOMatCard();
    card._config = { entry_id: "" };
    card._hass = {
      callWS: (msg) =>
        Promise.resolve(
          msg.type === "health_o_mat/list_persons"
            ? { persons: [{ entry_id: "entry-a" }, { entry_id: "entry-b" }] }
            : { person: "B", areas: { drink: true, bp: true, wellbeing: true } }
        ),
      states: {},
    };
    card._activeEntry = activeEntry;
    card._bpDraft = { sys: "120", dia: "80", pulse: "60", note: "Person A" };
    card._amountDraft = "250";
    card._bpError = "bp-fehler";
    card._amountError = "mengen-fehler";
    card._wbError = "wb-fehler";
    card._actionError = "aktions-fehler";
    return card;
  }

  function selectPerson(card, entry) {
    card._onSelectChange({
      target: { tagName: "SELECT", getAttribute: () => "person", value: entry },
    });
  }

  function snapshot(card) {
    return {
      activeEntry: card._activeEntry,
      bpDraft: card._bpDraft,
      amountDraft: card._amountDraft,
      bpError: card._bpError,
      amountError: card._amountError,
      wbError: card._wbError,
      actionError: card._actionError,
    };
  }

  const switched = makeCard("entry-a");
  selectPerson(switched, "entry-b");

  const reselected = makeCard("entry-a");
  selectPerson(reselected, "entry-a");

  __out = { switched: snapshot(switched), reselected: snapshot(reselected) };
  `,
  context,
  { filename: "card-person-switch-probe.js" }
);

process.stdout.write(JSON.stringify(context.__out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_card_person_switch_drops_person_scoped_drafts(tmp_path):
    """[F3] Ein echter Personenwechsel verwirft BD-/Mengen-Entwurf samt Fehlern.

    Kontrollfall: dieselbe Person erneut auszuwaehlen ist kein Wechsel und darf
    den Entwurf NICHT loeschen — sonst waere der Test auch mit einem pauschalen
    Aufraeumen gruen. Der Reload laeuft hier asynchron ins Leere; geprueft wird
    der synchrone Zustand direkt nach `_onSelectChange` (der Entwurf darf auch
    spaeter nicht wiederhergestellt werden — genau das verhindert der Fix).
    """
    module_path = tmp_path / "health-o-mat-card.js"
    module_path.write_bytes(Path(_CARD_JS).read_bytes())
    runner_path = tmp_path / "runner_card_person_switch.mjs"
    runner_path.write_text(_NODE_CARD_PERSON_SWITCH_RUNNER, encoding="utf-8")

    node = shutil.which("node") or "node"
    result = subprocess.run(
        [node, str(runner_path), str(module_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"Node-Runner fehlgeschlagen (rc={result.returncode}): {result.stderr}"
    )
    out = json.loads(result.stdout)

    switched = out["switched"]
    assert switched["activeEntry"] == "entry-b"
    assert switched["bpDraft"] is None, (
        f"der BD-Entwurf ueberlebt den Personenwechsel: {switched['bpDraft']!r}"
    )
    assert switched["amountDraft"] == ""
    for key in ("bpError", "amountError", "wbError", "actionError"):
        assert switched[key] == "", f"{key} ueberlebt den Personenwechsel: {switched[key]!r}"

    reselected = out["reselected"]
    assert reselected["activeEntry"] == "entry-a"
    assert reselected["bpDraft"]["sys"] == "120", (
        "das erneute Waehlen derselben Person loescht den Entwurf"
    )
    assert reselected["amountDraft"] == "250"
    assert reselected["actionError"] == "aktions-fehler"


def test_card_undo_is_disabled_when_no_drink_exists():
    """[Undo] Ohne Getränkebuchung wird der Button deaktiviert statt zu fehlern."""
    text = _card_source()
    action = _js_method_block(text, "_undoAction")
    undo = _js_method_block(text, "_undo")

    assert "this._data.undo.drink === false" in undo, (
        "der Undo-Aufruf prüft die serverseitige Verfügbarkeit nicht"
    )
    assert "canUndo" in action and "disabled" in action
    assert "Keine Getränkebuchung" in action


def test_card_person_filter_has_explicit_editing_state():
    """[Personen-Filter] 'Alle' abwählen startet eine leere, explizite Auswahl."""
    editor = _js_class_block(_card_source(), "HealthOMatCardEditor")
    toggle = _js_method_block(editor, "_togglePersonFilter")
    section = _js_method_block(editor, "_personSection")

    assert "_personFilterEditing = true" in toggle
    assert "_personFilterEditing = false" in toggle
    assert "filterIsAll" in section
    assert "disabled" in section, "die Einzelboxen sind bei 'Alle' nicht gesperrt"


# --- REQ-HOM-114: Wohlbefinden-Bestätigung vor Übernahme --------------------

_NODE_CARD_CONFIRM_RUNNER = """import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; }
  addEventListener() {}
  removeEventListener() {}
  querySelector(selector) {
    return String(selector).includes("wb-score") ? { value: "7" } : null;
  }
  querySelectorAll() { return []; }
  appendChild(child) { return child; }
}

class FakeHTMLElement {
  constructor() { this._shadow = null; }
  attachShadow() { this._shadow = new FakeShadowRoot(); return this._shadow; }
  get shadowRoot() { return this._shadow; }
  dispatchEvent() { return true; }
  setAttribute() {}
  removeAttribute() {}
}

const context = {
  HTMLElement: FakeHTMLElement,
  CustomEvent: class {
    constructor(type, init) {
      this.type = type;
      this.detail = init && init.detail ? init.detail : null;
    }
  },
  customElements: { get: () => undefined, define: () => {} },
  window: {},
  document: { createElement: () => ({}), addEventListener: () => {} },
  console: { info: () => {}, log: () => {}, warn: () => {}, error: () => {} },
  setTimeout: () => 0,
  clearTimeout: () => {},
  __out: null,
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "health-o-mat-card.js" });

const outPromise = vm.runInContext(
  `(async () => {
  function makeCard(confirm) {
    const card = new HealthOMatCard();
    card._config = { entry_id: "e1", wellbeing_confirm: confirm };
    card._data = { person: "Caro", wellbeing: { key: "bad", label: "Schlecht" } };
    card._activeEntry = "e1";
    card._render = () => {};
    card._loadData = () => Promise.resolve();
    card._calls = [];
    card._errors = 0;
    card._hass = {
      callWS: () => Promise.resolve({}),
      callService: (domain, service, payload) => {
        card._calls.push([domain, service, payload]);
        if (card._failNext) {
          card._failNext = false;
          return Promise.reject(new Error("Service nicht erreichbar"));
        }
        return Promise.resolve();
      },
      states: {},
    };
    return card;
  }

  function clickAction(card, action) {
    card._onCardClick({
      target: {
        closest: () => ({
          getAttribute: (name) => (name === "data-action" ? action : "good"),
        }),
      },
    });
  }

  const staged = makeCard(true);
  clickAction(staged, "wellbeing");
  const stagedHtml = staged._wellbeingInput();

  const immediate = makeCard(false);
  clickAction(immediate, "wellbeing");

  const confirmed = makeCard(true);
  clickAction(confirmed, "wellbeing");

  const score = makeCard(true);
  clickAction(score, "wellbeing-score");

  const failed = makeCard(true);
  failed._failNext = true;
  clickAction(failed, "wellbeing");

  const switched = makeCard(true);
  clickAction(switched, "wellbeing");
  switched._onSelectChange({
    target: { tagName: "SELECT", getAttribute: () => "person", value: "e2" },
  });

  const reconfigured = makeCard(true);
  clickAction(reconfigured, "wellbeing");
  reconfigured.setConfig({ entry_id: "e1", wellbeing_confirm: true });

  __out = {
    normalizer: {
      default: normalizeCardConfig({}).wellbeingConfirm,
      enabled: normalizeCardConfig({ wellbeing_confirm: true }).wellbeingConfirm,
      disabled: normalizeCardConfig({ wellbeing_confirm: false }).wellbeingConfirm,
    },
    staged: {
      pending: staged._wbPending,
      calls: staged._calls.slice(),
      html: stagedHtml,
    },
    immediate: { pending: immediate._wbPending, calls: immediate._calls.slice() },
    score: { pending: score._wbPending, calls: score._calls.slice() },
    switched: { pending: switched._wbPending },
    reconfigured: { pending: reconfigured._wbPending },
  };

  await confirmed._confirmWellbeing();
  __out.confirmed = { pending: confirmed._wbPending, calls: confirmed._calls };

  await score._confirmWellbeing();
  __out.score.confirmedCalls = score._calls;

  await failed._confirmWellbeing();
  __out.failed = { pending: failed._wbPending, error: failed._wbError };

  /* S2: Personenbezug der Vormerkung. */
  const filtered = makeCard(true);
  filtered._config = { person_mode: "selector", wellbeing_confirm: true };
  filtered._activeEntry = "e1";
  filtered._loadData = HealthOMatCard.prototype._loadData;
  filtered._hass = {
    callWS: (msg) =>
      msg.type === "health_o_mat/list_persons"
        ? Promise.resolve({ persons: [{ entry_id: "e2", display_name: "Dana" }] })
        : Promise.resolve({ person: "Dana", wellbeing: { key: "bad", label: "Schlecht" } }),
    callService: () => Promise.resolve(),
    states: {},
  };
  clickAction(filtered, "wellbeing");
  const filteredBefore = filtered._wbPending;
  await filtered._loadData();
  __out.filtered = {
    before: filteredBefore,
    pending: filtered._wbPending,
    activeEntry: filtered._activeEntry,
    html: filtered._wellbeingInput(),
  };

  const mismatched = makeCard(true);
  clickAction(mismatched, "wellbeing");
  mismatched._activeEntry = "e2";
  const mismatchedHtml = mismatched._wellbeingInput();
  await mismatched._confirmWellbeing();
  __out.mismatched = {
    pending: mismatched._wbPending,
    calls: mismatched._calls.slice(),
    html: mismatchedHtml,
  };

  /* S5: Editor-Schalter wirklich ausfuehren statt nur im Quelltext suchen. */
  const editor = new HealthOMatCardEditor();
  editor._config = { entry_id: "e1" };
  editor._render = () => {};
  const events = [];
  editor.dispatchEvent = (ev) => {
    events.push(ev);
    return true;
  };
  editor._toggleFlag("wellbeing_confirm", true);
  const editorOn = Object.assign({}, editor._config);
  const eventOn = events.length ? events[events.length - 1].detail.config : null;
  editor._toggleFlag("wellbeing_confirm", false);
  const editorOff = Object.assign({}, editor._config);
  const eventOff = events.length ? events[events.length - 1].detail.config : null;
  __out.editor = {
    on: editorOn,
    off: editorOff,
    eventOn,
    eventOff,
    hasOn: Object.prototype.hasOwnProperty.call(editorOn, "wellbeing_confirm"),
    hasOff: Object.prototype.hasOwnProperty.call(editorOff, "wellbeing_confirm"),
  };
  return __out;
  })()`,
  context,
  { filename: "card-confirm-probe.js" }
);

process.stdout.write(JSON.stringify(await outPromise));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_114_card_defers_wellbeing_report_until_confirmation(tmp_path):
    """[REQ-HOM-114] Karte: Klick/Absenden merkt vor, erst „Übernehmen" meldet.

    Kontrollfall `wellbeing_confirm=false`: die Meldung geht sofort raus.
    Fehlerfall: die Vormerkung bleibt für einen erneuten Versuch erhalten.
    """
    module_path = tmp_path / "health-o-mat-card.js"
    module_path.write_bytes(Path(_CARD_JS).read_bytes())
    runner_path = tmp_path / "runner_card_confirm.mjs"
    runner_path.write_text(_NODE_CARD_CONFIRM_RUNNER, encoding="utf-8")

    node = shutil.which("node") or "node"
    result = subprocess.run(
        [node, str(runner_path), str(module_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"Node-Runner fehlgeschlagen (rc={result.returncode}): {result.stderr}"
    )
    out = json.loads(result.stdout)

    assert out["normalizer"] == {"default": False, "enabled": True, "disabled": False}

    staged = out["staged"]
    assert staged["pending"] == {
        "entryId": "e1",
        "kind": "key",
        "key": "good",
        "score": None,
        "ts": "",
    }, "der Klick merkt die Auswahl nicht inkl. Personenbezug vor"
    assert staged["calls"] == [], "der Klick meldet trotz Bestätigungsmodus sofort"
    assert 'data-action="wellbeing-confirm"' in staged["html"], (
        "der Bestätigungsbutton fehlt bei bestehender Vormerkung"
    )
    assert "Übernehmen" in staged["html"]
    assert "noch nicht gemeldet" in staged["html"]
    assert re.search(r'class="wb-btn[^"]*pending[^"]*"', staged["html"]), (
        "die vorgemerkte Stufe ist nicht als `pending` markiert"
    )

    immediate = out["immediate"]
    assert len(immediate["calls"]) == 1, "ohne Bestätigungsmodus wird nicht sofort gemeldet"
    assert immediate["calls"][0][1] == "set_wellbeing"
    assert immediate["calls"][0][2]["status"] == "good"
    assert immediate["pending"] is None

    confirmed = out["confirmed"]
    assert len(confirmed["calls"]) == 1, "der Bestätigungsbutton meldet die Auswahl nicht"
    assert confirmed["calls"][0][2]["status"] == "good"
    assert confirmed["pending"] is None

    score = out["score"]
    assert score["pending"] == {
        "entryId": "e1",
        "kind": "score",
        "key": "",
        "score": 7,
        "ts": "",
    }, "die Zahleneingabe wird nicht vorgemerkt"
    assert score["calls"] == []
    assert score["confirmedCalls"][0][2]["score"] == 7

    assert out["switched"]["pending"] is None, "die Vormerkung überlebt den Personenwechsel"
    assert out["reconfigured"]["pending"] is None, "die Vormerkung überlebt `setConfig`"

    failed = out["failed"]
    assert failed["pending"] is not None, (
        "die Vormerkung geht bei einem Fehler verloren (kein erneuter Versuch möglich)"
    )
    assert failed["error"]

    # S2: Personenbezug — eine Vormerkung gilt nur fuer die Person, fuer die
    # sie entstanden ist. Wechselt `_activeEntry` ohne `_onSelectChange`
    # (Person faellt aus Filter/Liste), wird sie verworfen.
    filtered = out["filtered"]
    assert filtered["before"]["entryId"] == "e1"
    assert filtered["activeEntry"] == "e2"
    assert filtered["pending"] is None, (
        "die Vormerkung ueberlebt einen Personenwechsel in `_loadData`"
    )
    assert 'data-action="wellbeing-confirm"' not in filtered["html"], (
        "eine verworfene Vormerkung wird weiterhin als bestaetigbar gerendert"
    )

    # Ohne `_loadData` (nur `_activeEntry` veraendert) darf eine fremde
    # Vormerkung weder gerendert noch uebernommen werden.
    mismatched = out["mismatched"]
    assert 'data-action="wellbeing-confirm"' not in mismatched["html"]
    assert "noch nicht gemeldet" not in mismatched["html"]
    assert mismatched["calls"] == [], "die Bestaetigung meldet eine Vormerkung einer anderen Person"


def test_req_hom_114_card_confirm_button_needs_pending_selection():
    """[REQ-HOM-114] Bestätigungsbutton hängt an einer Vormerkung, nicht am Modus."""
    text = _card_source()
    form = _js_method_block(text, "_wellbeingInput")
    confirm = _js_method_block(text, "_confirmWellbeing")
    click = _js_method_block(text, "_onCardClick")

    assert "this._wbPending" in form
    assert "staged" in form and "confirmRow" in form
    assert 'data-action="wellbeing-confirm"' in form
    # Nur bei aktiver Option UND vorhandener Vormerkung der aktiven Person.
    assert "this._wellbeingConfirmEnabled() ? this._wbPendingFor() : null" in form
    assert "const confirmRow = staged" in form
    # Erst die Bestätigung ruft die Meldung auf.
    assert "_reportWellbeing" in confirm and "_reportWellbeingScore" in confirm
    assert re.search(r'action === "wellbeing-confirm"[\s\S]*?_confirmWellbeing\(\)', click), (
        "der Klick auf 'Übernehmen' ruft nicht `_confirmWellbeing()` auf"
    )


def test_req_hom_114_card_editor_has_wellbeing_confirm_checkbox():
    """[REQ-HOM-114] Editor: eigener Schalter mit Default `false`."""
    text = _card_source()
    editor = _js_class_block(text, "HealthOMatCardEditor")
    inputs = _js_method_block(editor, "_inputSection")
    toggle = _js_method_block(editor, "_toggleFlag")

    assert 'data-key="wellbeing_confirm"' in inputs
    assert "Wohlbefinden: Bestätigung vor Übernahme" in inputs
    assert "_effectiveWellbeingConfirm()" in inputs
    # Eigener Zweig: an setzt explizit `true`, aus entfernt den Key (Default false).
    assert re.search(r'key === "wellbeing_confirm"', toggle)
    assert re.search(r"if\s*\(\s*checked\s*\)\s*next\[key\]\s*=\s*true", toggle)
    assert re.search(r"else\s+delete\s+next\[key\]", toggle)
    # NICHT in der `show_*`-Liste (die ist auf die neun Schema-Schalter gepinnt).
    show_keys = re.search(r"CARD_SHOW_KEYS\s*=\s*\[(.*?)\]", text, re.S)
    assert show_keys is not None
    assert "wellbeing_confirm" not in show_keys.group(1)
    assert "wellbeingConfirm: toBool(source.wellbeing_confirm, false)" in text


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_114_card_editor_toggle_writes_config(tmp_path):
    """[REQ-HOM-114] Editor: `_toggleFlag` setzt `true` bzw. löscht den Key."""
    module_path = tmp_path / "health-o-mat-card.js"
    module_path.write_bytes(Path(_CARD_JS).read_bytes())
    runner_path = tmp_path / "runner_card_confirm.mjs"
    runner_path.write_text(_NODE_CARD_CONFIRM_RUNNER, encoding="utf-8")

    node = shutil.which("node") or "node"
    result = subprocess.run(
        [node, str(runner_path), str(module_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"Node-Runner fehlgeschlagen (rc={result.returncode}): {result.stderr}"
    )
    editor = json.loads(result.stdout)["editor"]

    assert editor["hasOn"] is True, "der Schalter setzt `wellbeing_confirm` nicht"
    assert editor["on"]["wellbeing_confirm"] is True
    assert editor["eventOn"]["wellbeing_confirm"] is True, (
        "`config-changed` traegt den neuen Schalter nicht"
    )
    assert editor["hasOff"] is False, "Ausschalten muss den Key entfernen (Default ist `false`)"
    assert editor["eventOff"].get("wellbeing_confirm") is None


# --- REQ-HOM-120: Rückdatierung in der Karte --------------------------------

_NODE_CARD_TS_RUNNER = """import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; this._fields = {}; }
  addEventListener() {}
  removeEventListener() {}
  querySelector(selector) {
    const match = /\\[data-role="([^"]+)"\\]/.exec(String(selector));
    const field = match ? match[1] : "";
    return this._fields[field] || null;
  }
  querySelectorAll() { return []; }
  appendChild(child) { return child; }
}

class FakeHTMLElement {
  constructor() { this._shadow = null; }
  attachShadow() { this._shadow = new FakeShadowRoot(); return this._shadow; }
  get shadowRoot() { return this._shadow; }
  dispatchEvent() { return true; }
  setAttribute() {}
  removeAttribute() {}
}

const context = {
  HTMLElement: FakeHTMLElement,
  CustomEvent: class {
    constructor(type, init) {
      this.type = type;
      this.detail = init && init.detail ? init.detail : null;
    }
  },
  customElements: { get: () => undefined, define: () => {} },
  window: {},
  document: { createElement: () => ({}), addEventListener: () => {} },
  console: { info: () => {}, log: () => {}, warn: () => {}, error: () => {} },
  setTimeout: () => 0,
  clearTimeout: () => {},
  __out: null,
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "health-o-mat-card.js" });

const outPromise = vm.runInContext(
  `(async () => {
  function makeCard(confirm) {
    const card = new HealthOMatCard();
    card._config = { entry_id: "e1", wellbeing_confirm: confirm };
    card._data = { person: "Caro", wellbeing: { key: "bad", label: "Schlecht" } };
    card._activeEntry = "e1";
    card._render = () => {};
    card._loadData = () => Promise.resolve();
    card._calls = [];
    card._hass = {
      callWS: () => Promise.resolve({}),
      callService: (domain, service, payload) => {
        card._calls.push([domain, service, payload]);
        return Promise.resolve();
      },
      states: {},
    };
    card.shadowRoot._fields = {
      "drink-ts": { value: "" },
      "bp-ts": { value: "" },
      "wb-ts": { value: "" },
      "bp-sys": { value: "120" },
      "bp-dia": { value: "80" },
      "bp-pulse": { value: "" },
      "bp-note": { value: "" },
    };
    return card;
  }

  const drink = makeCard(false);
  drink.shadowRoot._fields["drink-ts"].value = "2026-10-24T18:30";
  await drink._book(250, "Wasser");
  const drinkResult = {
    calls: drink._calls,
    draft: drink._tsDraft["drink-ts"],
    field: drink.shadowRoot._fields["drink-ts"].value,
  };

  const future = makeCard(false);
  future.shadowRoot._fields["drink-ts"].value = "2999-01-01T10:00";
  await future._book(250, "Wasser");
  const futureResult = { calls: future._calls, error: future._actionError };

  const bp = makeCard(false);
  bp.shadowRoot._fields["bp-ts"].value = "2026-10-24T07:15";
  await bp._saveBp();
  const bpResult = { calls: bp._calls, draft: bp._tsDraft["bp-ts"] };

  const wb = makeCard(true);
  wb.shadowRoot._fields["wb-ts"].value = "2026-10-23T20:00";
  wb._stageWellbeing("great", null);
  const wbStaged = { pending: wb._wbPending, calls: wb._calls.slice() };
  await wb._confirmWellbeing();
  const wbConfirmed = { pending: wb._wbPending, calls: wb._calls };

  const wbFuture = makeCard(false);
  wbFuture.shadowRoot._fields["wb-ts"].value = "2999-01-01T10:00";
  await wbFuture._reportWellbeing("great");
  const wbFutureResult = { calls: wbFuture._calls, error: wbFuture._wbError };

  __out = {
    drink: drinkResult,
    future: futureResult,
    bp: bpResult,
    wbStaged,
    wbConfirmed,
    wbFuture: wbFutureResult,
  };
  return __out;
  })()`,
  context,
  { filename: "card-ts-probe.js" }
);

process.stdout.write(JSON.stringify(await outPromise));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_120_card_sends_ts_and_validates_future(tmp_path):
    """[REQ-HOM-120] Karte: ts in allen drei Schreibpfaden, Zukunft blockiert."""
    module_path = tmp_path / "health-o-mat-card.js"
    module_path.write_bytes(Path(_CARD_JS).read_bytes())
    runner_path = tmp_path / "runner_card_ts.mjs"
    runner_path.write_text(_NODE_CARD_TS_RUNNER, encoding="utf-8")

    node = shutil.which("node") or "node"
    result = subprocess.run(
        [node, str(runner_path), str(module_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"Node-Runner fehlgeschlagen (rc={result.returncode}): {result.stderr}"
    )
    out = json.loads(result.stdout)

    drink = out["drink"]
    assert len(drink["calls"]) == 1
    assert drink["calls"][0][1] == "add_drink"
    assert drink["calls"][0][2]["ts"]
    assert drink["draft"] == "", "der Zeitpunkt-Entwurf wird nach Erfolg nicht geleert"
    assert drink["field"] == ""

    future = out["future"]
    assert future["calls"] == [], "ein Zukunft-Zeitpunkt wird trotzdem gebucht"
    assert "Zukunft" in future["error"]

    bp = out["bp"]
    assert len(bp["calls"]) == 1 and bp["calls"][0][1] == "add_blood_pressure"
    assert bp["calls"][0][2]["ts"]
    assert bp["draft"] == ""

    staged = out["wbStaged"]
    assert staged["calls"] == [], "die Vormerkung meldet trotz Bestätigungsmodus sofort"
    assert staged["pending"]["ts"], "die Vormerkung trägt keinen Zeitpunkt"

    confirmed = out["wbConfirmed"]
    assert len(confirmed["calls"]) == 1 and confirmed["calls"][0][1] == "set_wellbeing"
    assert confirmed["calls"][0][2]["ts"]
    assert confirmed["pending"] is None

    wb_future = out["wbFuture"]
    assert wb_future["calls"] == []
    assert "Zukunft" in wb_future["error"]


def test_req_hom_120_card_renders_ts_fields_in_all_three_blocks():
    """[REQ-HOM-120] Karte: kompaktes `datetime-local` in Getränk/BD/Wohlbefinden."""
    text = _card_source()

    assert 'this._tsFieldHtml("drink-ts")' in _js_method_block(text, "_drinkActions")
    assert 'this._tsFieldHtml("drink-ts")' in _js_method_block(text, "_manualAmounts")
    assert 'this._tsFieldHtml("bp-ts")' in _js_method_block(text, "_bloodPressureInput")
    assert 'this._tsFieldHtml("wb-ts")' in _js_method_block(text, "_wellbeingInput")

    field = _js_method_block(text, "_tsFieldHtml")
    assert '<label class="field">' in field, "das Feld nutzt nicht das kompakte Feld-Layout"
    assert 'type="datetime-local"' in field
    assert 'data-role="${role}"' in field
    # Leer = jetzt (kein stiller Fallback auf eine erfundene Zeit).
    assert "leer = jetzt" in field


def test_req_hom_120_card_payloads_carry_ts():
    """[REQ-HOM-120] Alle drei Service-Payloads senden `ts` nur wenn gesetzt."""
    text = _card_source()

    assert re.search(r'_readEntryTs\(\s*"drink-ts"\s*\)', _js_method_block(text, "_book"))
    assert re.search(r"payload\.ts\s*=\s*ts\.iso", _js_method_block(text, "_book"))
    assert re.search(r'_readEntryTs\(\s*"bp-ts"\s*\)', _js_method_block(text, "_saveBp"))
    assert re.search(r"payload\.ts\s*=\s*ts\.iso", _js_method_block(text, "_saveBp"))

    stage = _js_method_block(text, "_stageWellbeing")
    assert 'this._readEntryTs("wb-ts")' in stage
    assert "ts: ts.iso" in stage
    confirm = _js_method_block(text, "_confirmWellbeing")
    assert "pending.ts" in confirm
    report = _js_method_block(text, "_reportWellbeing")
    assert "timestamp" in report and "payload.ts" in report


def test_req_hom_120_card_time_label_relative_then_absolute():
    """[REQ-HOM-120] Karte: frisch relativ, älter als 24 h absolut."""
    text = _card_source()

    label = _js_method_block(text, "_timeLabel")
    assert "this._relativeTime(iso)" in label
    assert "24 * 60 * 60 * 1000" in label
    assert "pad(date.getDate())" in label
    # Beide Anzeigepfade (BD, Wohlbefinden) nutzen den Helfer.
    assert "_timeLabel(bp.at)" in text
    assert "_timeLabel(wb.at)" in text


# --- M3b: Undo für alle Typen + optionaler Verlauf --------------------------


def test_card_show_history_defaults_to_false_and_is_not_a_show_key():
    """[M3b] `show_history` ist Default AUS und unabhängig von CARD_SHOW_KEYS."""
    text = _card_source()
    normalizer = _js_function_block(text, "normalizeCardConfig")
    keys = re.search(r"CARD_SHOW_KEYS\s*=\s*\[(.*?)\]", text, re.S)
    assert keys is not None
    assert "show_history" not in keys.group(1), "show_history darf nicht in CARD_SHOW_KEYS stehen"
    assert re.search(r"showHistory:\s*toBool\(\s*source\.show_history\s*,\s*false\s*\)", normalizer)

    editor = _js_class_block(text, "HealthOMatCardEditor")
    inputs = _js_method_block(editor, "_inputSection")
    assert 'data-key="show_history"' in inputs
    assert "Verlauf anzeigen (letzte 5)" in inputs
    assert 'key === "show_history"' in _js_method_block(editor, "_toggleFlag")


def test_card_undo_and_history_use_the_expected_commands():
    """[M3b] Card: kind-basiertes Undo, list_history mit include_voided."""
    text = _card_source()
    undo = _js_method_block(text, "_undo")
    load = _js_method_block(text, "_loadHistory")

    assert "remove_last_entry" in undo
    assert "kind: undoKind" in undo
    assert '"blood_pressure"' in undo and '"wellbeing"' in undo
    assert "list_history" in load
    assert "include_voided: true" in load, (
        "die Karte kann gelöschte Einträge nicht wiederherstellen"
    )
    assert "history-void-confirm" in _js_method_block(text, "_historyBlock")
    assert "Wirklich löschen?" in _js_method_block(text, "_historyBlock")
    assert "history-restore" in _js_method_block(text, "_historyBlock")


_NODE_CARD_HISTORY_RUNNER = """import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; }
  addEventListener() {}
  removeEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
}
class FakeHTMLElement {
  constructor() { this._shadow = null; }
  attachShadow() { this._shadow = new FakeShadowRoot(); return this._shadow; }
  get shadowRoot() { return this._shadow; }
  setAttribute() {}
  removeAttribute() {}
  dispatchEvent() { return true; }
}
const context = {
  HTMLElement: FakeHTMLElement,
  CustomEvent: class {
    constructor(type, init) { this.type = type; this.detail = init && init.detail; }
  },
  customElements: { get: () => undefined, define: () => {} },
  window: {},
  document: { createElement: () => ({}), addEventListener: () => {} },
  console: { info: () => {}, log: () => {}, warn: () => {}, error: () => {} },
  setTimeout: () => 0,
  clearTimeout: () => {},
  __out: null,
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "health-o-mat-card.js" });

const promise = vm.runInContext(
  `(async () => {
  function makeCard() {
    const card = new HealthOMatCard();
    card._config = { entry_id: "e1", show_history: true };
    card._activeEntry = "e1";
    card._data = {
      person: "Caro",
      person_anchor: "caro",
      undo: { drink: true, blood_pressure: true },
      wellbeing: { key: "good", at: "2026-10-19T18:00:00+02:00" },
      areas: { drink: true, bp: true, wellbeing: true },
      wellbeing_scale: [
        { key: "bad", label: "Schlecht" },
        { key: "good", label: "Gut" },
      ],
    };
    card._render = () => {};
    card._loads = 0;
    card._loadData = () => { card._loads += 1; return Promise.resolve(); };
    card._calls = [];
    card._wsCalls = [];
    card._payloads = {
      drinks: Array.from({ length: 7 }, (_, i) => ({
        id: "d" + i,
        ts: "2026-10-19T0" + (i % 9) + ":00:00+02:00",
        ml: 200,
        type: "Wasser",
        voided_at: i === 1 ? "2026-10-19T10:00:00+02:00" : null,
      })),
      blood_pressure: [{ id: "b1", ts: "2026-10-19T07:00:00+02:00", sys: 120, dia: 80 }],
      wellbeing: [{ id: "w1", ts: "2026-10-19T18:00:00+02:00", key: "good" }],
    };
    card._hass = {
      callService: (domain, service, payload) => {
        card._calls.push([domain, service, payload]);
        return Promise.resolve();
      },
      callWS: (msg) => {
        card._wsCalls.push(msg);
        if (msg.type === "health_o_mat/list_history") {
          return Promise.resolve({ kind: msg.kind, entries: card._payloads[msg.kind] || [] });
        }
        return Promise.resolve({});
      },
      states: {},
    };
    return card;
  }

  const history = makeCard();
  await history._loadHistory();
  const loaded = {
    calls: history._wsCalls.slice(),
    drinks: history._history.drinks.entries.length,
    voidedVisible: history._history.drinks.entries.some((entry) => entry.voided_at),
  };

  const blockCard = makeCard();
  blockCard._history = {
    drinks: {
      entries: blockCard._payloads.drinks.slice(0, 2),
      loading: false,
      loaded: true,
      error: "",
    },
  };
  const blockHtml = blockCard._historyBlock("drinks");
  blockCard._beginHistoryVoid("drinks", "d0");
  const confirmHtml = blockCard._historyBlock("drinks");

  const voided = makeCard();
  await voided._setHistoryEntryVoided("drinks", "d0", false);
  const voidResult = {
    call: voided._wsCalls[0],
    loads: voided._loads,
    confirm: voided._historyConfirm,
  };

  const restored = makeCard();
  await restored._setHistoryEntryVoided("drinks", "d1", true);
  const restoreResult = { call: restored._wsCalls[0], loads: restored._loads };

  const undoBp = makeCard();
  undoBp._history.blood_pressure = { entries: [{ id: "b1" }], loading: false, loaded: true };
  await undoBp._undo("blood_pressure");

  const undoWb = makeCard();
  undoWb._history.wellbeing = { entries: [{ id: "w1" }], loading: false, loaded: true };
  await undoWb._undo("wellbeing");

  const editor = new HealthOMatCardEditor();
  editor._config = { entry_id: "e1" };
  editor._render = () => {};
  const events = [];
  editor.dispatchEvent = (event) => { events.push(event); return true; };
  editor._toggleFlag("show_history", true);
  const on = Object.assign({}, editor._config);
  const eventOn = events[events.length - 1].detail.config;
  editor._toggleFlag("show_history", false);
  const off = Object.assign({}, editor._config);

  __out = {
    normalizer: {
      default: normalizeCardConfig({}).showHistory,
      enabled: normalizeCardConfig({ show_history: true }).showHistory,
    },
    loaded,
    blockHtml,
    confirmHtml,
    htmlWithoutHistory: (() => {
      const plain = makeCard();
      plain._config = { entry_id: "e1" };
      return plain._historyBlock("drinks");
    })(),
    voidResult,
    restoreResult,
    undoBp: undoBp._calls,
    undoWb: undoWb._calls,
    editor: {
      on,
      off,
      eventOn,
      hasOn: Object.prototype.hasOwnProperty.call(on, "show_history"),
      hasOff: Object.prototype.hasOwnProperty.call(off, "show_history"),
    },
  };
  return __out;
  })()`,
  context,
  { filename: "card-history-probe.js" }
);
process.stdout.write(JSON.stringify(await promise));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_card_history_and_undo_for_all_kinds(tmp_path):
    """[M3b] History lädt inkl. gelöschter Einträge, Void/Restore + Undo BP/WB."""
    module_path = tmp_path / "health-o-mat-card.js"
    module_path.write_bytes(Path(_CARD_JS).read_bytes())
    runner_path = tmp_path / "runner_card_history.mjs"
    runner_path.write_text(_NODE_CARD_HISTORY_RUNNER, encoding="utf-8")

    node = shutil.which("node") or "node"
    result = subprocess.run(
        [node, str(runner_path), str(module_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"Node-Runner fehlgeschlagen (rc={result.returncode}): {result.stderr}"
    )
    out = json.loads(result.stdout)

    assert out["normalizer"] == {"default": False, "enabled": True}
    loaded = out["loaded"]
    assert [call["kind"] for call in loaded["calls"]] == [
        "drinks",
        "blood_pressure",
        "wellbeing",
    ]
    assert all(call["include_voided"] is True for call in loaded["calls"])
    assert loaded["drinks"] == 5, "die Karte zeigt nicht maximal 5 Einträge"
    assert loaded["voidedVisible"] is True, "gelöschte Einträge fehlen im Kartenverlauf"

    assert 'data-history="drinks"' in out["blockHtml"]
    assert "Wasser" in out["blockHtml"] and "gelöscht" in out["blockHtml"]
    assert 'data-action="history-restore"' in out["blockHtml"]
    assert 'data-action="history-void"' in out["blockHtml"]
    assert "Wirklich löschen?" in out["confirmHtml"]
    assert 'data-action="history-void-confirm"' in out["confirmHtml"]
    assert out["htmlWithoutHistory"] == "", "show_history=false rendert dennoch einen Verlauf"

    assert out["voidResult"]["call"]["type"] == "health_o_mat/void_entry"
    assert out["voidResult"]["call"]["item_id"] == "d0"
    assert out["voidResult"]["loads"] == 1
    assert out["voidResult"]["confirm"] is None
    assert out["restoreResult"]["call"]["type"] == "health_o_mat/restore_entry"
    assert out["restoreResult"]["call"]["item_id"] == "d1"

    assert out["undoBp"] == [
        ["health_o_mat", "remove_last_entry", {"person": "caro", "kind": "blood_pressure"}]
    ]
    assert out["undoWb"] == [
        ["health_o_mat", "remove_last_entry", {"person": "caro", "kind": "wellbeing"}]
    ]

    editor = out["editor"]
    assert editor["hasOn"] is True and editor["on"]["show_history"] is True
    assert editor["eventOn"].get("show_history") is True
    assert editor["hasOff"] is False, "Ausschalten muss den Key entfernen (Default false)"


# --- REQ-HOM-117: card UI translations (inline loader) ---------------------

_NODE_CARD_I18N_RUNNER = """import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");
const resources = JSON.parse(process.argv[3]);
const context = {
  HTMLElement: class HTMLElement {},
  customElements: {
    _classes: {},
    get() { return undefined; },
    define(tag, cls) { this._classes[tag] = cls; },
  },
  window: {},
  document: { createElement: () => ({}) },
  console: { info: () => {}, log: () => {}, warn: () => {}, error: () => {} },
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "health-o-mat-card.js" });

await context._loadUiTranslations({ language: "de", callWS: async () => ({ resources: {} }) });
const german = context._t("ui_card_goal", "Ziel");

await context._loadUiTranslations({ language: "en", callWS: async () => ({ resources }) });
const english = context._t("ui_card_goal", "Ziel");
const interpolated = context._t("ui_card_book_aria", "{label} mit {ml} Milliliter buchen", {
  label: "Coffee",
  ml: 250,
});
const rawKey = context._t("ui_missing");
const scale = context.customElements._classes["health-o-mat-card"].prototype._wellbeingScale.call({
  _data: { wellbeing_scale: [{ key: "good", label: "Gut" }] },
});

process.stdout.write(JSON.stringify({ german, english, interpolated, rawKey, scale }));
"""


def _run_node(tmp_path, runner_source: str, args: list[str], name: str) -> str:
    """Fuehrt einen Node-Runner aus und liefert dessen stdout."""
    runner_path = tmp_path / f"{name}.mjs"
    runner_path.write_text(runner_source, encoding="utf-8")
    result = subprocess.run(
        [shutil.which("node") or "node", str(runner_path), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"Node-Runner {name} fehlgeschlagen (rc={result.returncode}): {result.stderr}"
    )
    return result.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_117_card_inline_translations_and_language_switch(tmp_path):
    """[REQ-HOM-117] Karte: inline Loader, Interpolation, Fallback, en-Label."""
    resources = {
        "component.health_o_mat.common.ui_card_goal": "Goal",
        "component.health_o_mat.common.ui_common_wb_good": "Good",
    }
    out = json.loads(
        _run_node(
            tmp_path,
            _NODE_CARD_I18N_RUNNER,
            [str(Path(_CARD_JS)), json.dumps(resources)],
            "runner_i18n_card",
        )
    )

    assert out["german"] == "Ziel", "der deutsche Fallback geht verloren"
    assert out["english"] == "Goal", "der Sprachwechsel greift nicht"
    assert out["interpolated"] == "Coffee mit 250 Milliliter buchen", (
        "`{platzhalter}` wird nicht interpoliert"
    )
    assert out["rawKey"] == "", "ein fehlender Key darf nie roh angezeigt werden"
    assert out["scale"][0]["label"] == "Good", (
        "das Server-Wellbeing-Label wird nicht per Key übersetzt"
    )


# --- REQ-HOM-122: Laborwerte-Karte (standalone Lovelace card) ---------------

_LABS_CARD_JS = os.path.join(
    _REPO_ROOT,
    "custom_components",
    "health_o_mat",
    "www",
    "health-o-mat-labs-card.js",
)


def _labs_card_source() -> str:
    with open(_LABS_CARD_JS, encoding="utf-8") as handle:
        return handle.read()


def test_req_hom_122_labs_card_file_exists_and_defines_custom_element():
    source = _labs_card_source()
    assert 'customElements.define("health-o-mat-labs-card"' in source


def test_req_hom_122_labs_card_defines_editor():
    source = _labs_card_source()
    assert "class HealthOMatLabsCardEditor" in source


def test_req_hom_122_labs_card_supports_person_mode_and_filter():
    source = _labs_card_source()
    assert "person_mode" in source
    assert "person_filter" in source
    assert "default_person" in source


def test_req_hom_122_labs_card_calls_ws_not_service():
    source = _labs_card_source()
    assert "sendMessagePromise" in source
    assert "callService" not in source


def test_req_hom_122_labs_card_has_disclaimer_flag():
    source = _labs_card_source()
    assert "show_disclaimer" in source


def test_req_hom_122_labs_card_editor_schema_has_five_keys():
    """entry_id/person_mode-family aside,
    show_categories/show_trend/allow_manual_entry/show_disclaimer (§7.1 editor table)."""
    source = _labs_card_source()
    for key in ("show_categories", "show_trend", "allow_manual_entry", "show_disclaimer"):
        assert key in source, key


def test_req_hom_122_labs_card_is_standalone_vanilla_module():
    """[REQ-HOM-122] Die Karte importiert das Panel-Modul NICHT (eigene Helfer)."""
    source = _labs_card_source()
    assert re.search(r"^\s*import\s", source, re.M) is None
    assert "require(" not in source
    assert "health-o-mat-panel-base" not in source
    for name in (
        "escapeHtml",
        "labBadge",
        "labReportedSubline",
        "labSparkline",
        "labMarkerOptionsHtml",
    ):
        assert re.search(rf"function\s+{name}\s*\(", source), f"{name}() fehlt in der Karte"


# --- REQ-HOM-122: Sprachabhaengige Katalog-Namen in der Labor-Karte ---------

_NODE_LABS_CARD_I18N_RUNNER = """import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; }
  addEventListener() {}
  removeEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
}

class FakeHTMLElement {
  constructor() { this._shadow = null; }
  attachShadow() { this._shadow = new FakeShadowRoot(); return this._shadow; }
  get shadowRoot() { return this._shadow; }
}

const context = {
  HTMLElement: FakeHTMLElement,
  customElements: {
    _classes: {},
    get() { return undefined; },
    define(tag, cls) { this._classes[tag] = cls; },
  },
  window: {},
  document: { createElement: () => ({}) },
  console: { info: () => {}, log: () => {}, warn: () => {}, error: () => {} },
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "health-o-mat-labs-card.js" });

const CardClass = context.customElements._classes["health-o-mat-labs-card"];
const labs = {
  categories: [
    { key: "liver", name: "Leber", name_de: "Leber", name_en: "Liver", hidden: false },
  ],
  markers: {
    alt: {
      category: "liver",
      name: "ALT (GPT)",
      name_de: "ALT (GPT)",
      name_en: "ALT (ALT/GPT)",
      unit: "U/L",
      value: 12,
      ref_min: 10,
      ref_max: 50,
      in_range: true,
      history: [],
    },
  },
};

function render(language) {
  const card = new CardClass();
  card._config = {
    entry_id: "entry-1",
    person_mode: "fixed",
    show_trend: false,
    allow_manual_entry: false,
    show_disclaimer: false,
  };
  card._normalized = null;
  card._data = { person: "Alex", labs };
  card.hass = { language };
  card._render();
  return card.shadowRoot.innerHTML;
}

process.stdout.write(JSON.stringify({ de: render("de"), en: render("en-US") }));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_122_labs_card_renders_localized_catalog_names(tmp_path):
    """[REQ-HOM-122] Die Karte zeigt im EN-Fall `name_en`, im DE-Fall `name_de`."""
    out = json.loads(
        _run_node(
            tmp_path,
            _NODE_LABS_CARD_I18N_RUNNER,
            [str(Path(_LABS_CARD_JS))],
            "runner_labs_card_i18n",
        )
    )

    assert "Leber" in out["de"] and "ALT (GPT)" in out["de"]
    assert "Liver" not in out["de"], "englischer Kategoriename erscheint bei deutscher UI"
    assert "Liver" in out["en"], "die Karte ignoriert `name_en` bei englischer UI"
    assert "ALT (ALT/GPT)" in out["en"], "der englische Marker-Name fehlt"
    assert "Leber" not in out["en"], "deutscher Kategoriename bleibt bei englischer UI"

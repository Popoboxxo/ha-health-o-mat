"""Tests: www/health-o-mat-card.js — statische Regressionen (kein JS-Runner).

Die Karte ist ein Vanilla-Web-Component ohne Build-Toolchain. Diese Tests
sichern die Eigenschaften, die bei Refactorings still kaputtgehen können, als
Text-Assertions auf die Quelldatei:

* die Karte referenziert ausschließlich die erlaubten `health_o_mat/*`-WS-
  Kommandos (keine Admin-/Settings-Kommandos),
* das `areas`-Gating (Bereiche ausblenden) ist vorhanden,
* die Map der freundlichen Blutdruck-Kategorielabels deckt alle sieben Keys ab.

Absichtlich tolerant gegenüber Formatierung: es wird nur der Dateitext gelesen.
"""

from __future__ import annotations

import os
import re

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CARD_JS = os.path.join(
    _REPO_ROOT, "custom_components", "health_o_mat", "www", "health-o-mat-card.js"
)

# Erlaubte WS-Kommandos der eingebetteten Karte (nur lesend, kein Admin).
_ALLOWED_WS_COMMANDS = {"list_persons", "panel_data", "subscribe"}

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
    assert re.search(r"\$\{score\}\s*/\s*\$\{WELLBEING_SCALE\.length\}", text), (
        "Das Score-Badge zeigt den Score nicht gegen das Skalenmaximum"
    )


def test_card_wellbeing_chart_needs_no_external_library():
    """[REQ-HOM-112] Keine externe Bibliothek für Score/Sparkline (Vanilla)."""
    text = _card_source()

    assert re.search(r"^\s*import\s", text, re.M) is None
    assert "require(" not in text


# --- REQ-HOM-112: Quelltext-Assertions zur Series-Logik der Karte -------------
#
# Die Historie ist ein Wechsel-Protokoll (siehe `store.set_wellbeing`): ein
# Eintrag bedeutet "bis zu diesem Zeitpunkt galt dieser Status", der AKTUELLE
# Zustand steht ausschliesslich im `wellbeing`-Block. Die Sparkline muss den
# aktuellen Wert an die Serie anhaengen — sonst endet sie am abgeloesten Wert
# und widerspricht dem Badge.


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
        r'<span class="score">\$\{score\}\s*/\s*\$\{WELLBEING_SCALE\.length\}</span>',
        text,
    ), "das Score-Badge nutzt nicht den aufgeloesten Score"

"""Frontend-Smoke-Guard: Cache-Buster der Panel-Module == manifest.version.

Läuft ohne Home-Assistant-Runtime über die Fake-Package-Technik aus
`tests/conftest.py`: `homeassistant.*` wird für den Import von `frontend.py`
durch Minimal-Fakes ersetzt (echter Import gewinnt, falls HA installiert ist).
Die eigentliche Prüfung ist reine Dateianalyse der Panel-JS-Module.

Der Test koppelt die JS-Module an die Integrationsversion: eine Release-Anhebung
in `manifest.json` ohne gleichzeitige Anpassung der Versions-Query in den
Modul-Imports (stiller Cache-Buster-Drift, weil `www/` mit `cache_headers=True`
ausgeliefert wird) lässt ihn fehlschlagen.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)
_WWW_DIR = Path(_COMPONENT_DIR) / "www"

# Fake-Paket für die relativen Imports von frontend.py
_PKG = "_hom_panel_js_test_pkg"
_pkg = types.ModuleType(_PKG)
_pkg.__path__ = [_COMPONENT_DIR]
sys.modules.setdefault(_PKG, _pkg)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.{name}", os.path.join(_COMPONENT_DIR, f"{name}.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.{name}"] = module
    spec.loader.exec_module(module)
    return module


frontend = _load("frontend")

# Version-Query in einem Import-Specifier (`?v=1.2.3`); stoppt an Anführungs-
# zeichen, Whitespace, Klammern und `&`/`>`.
_VERSION_QUERY_RE = re.compile(r"\?v=([^\"'\s)>&]+)")
_PANEL_TAG_RE = re.compile(r"""PANEL_TAG\s*=\s*["']health-o-mat-panel["']""")


def _panel_modules() -> list[Path]:
    return sorted(_WWW_DIR.glob("health-o-mat-panel*.js"))


def test_panel_modules_exist():
    """Entry-Modul + mindestens ein Split-Modul sind vorhanden."""
    names = {path.name for path in _panel_modules()}
    assert "health-o-mat-panel.js" in names, "Entry-Modul fehlt unter www/"
    assert len(names) > 1, "Panel wurde nicht in ES-Module aufgeteilt"


def test_entry_module_defines_panel_tag():
    """Der registrierte Webcomponent-Name bleibt im Entry-Modul verankert."""
    entry = (_WWW_DIR / "health-o-mat-panel.js").read_text(encoding="utf-8")
    assert _PANEL_TAG_RE.search(entry), "PANEL_TAG = 'health-o-mat-panel' fehlt im Entry-Modul"


def test_every_version_query_matches_manifest_version():
    """Jede `?v=<version>`-Angabe der Panel-Module == manifest.version."""
    version = frontend.integration_version()
    assert version and version != "0", "manifest.json lieferte keine brauchbare Version"

    literals: list[tuple[str, str]] = []
    for path in _panel_modules():
        text = path.read_text(encoding="utf-8")
        for match in _VERSION_QUERY_RE.finditer(text):
            literals.append((path.name, match.group(1)))

    assert literals, "keine Versions-Query in den Panel-Modulen gefunden"
    mismatches = [(name, value) for name, value in literals if value != version]
    assert not mismatches, f"Cache-Buster != manifest.version {version!r}: {mismatches}"


# --- REQ-HOM-112: Wohlbefinden-Score-Chart im Panel -------------------------

# Chart-Helper des Basis-Moduls (Wohlbefinden-Tab).
_WELLBEING_CHART_HELPERS = (
    "wellbeingChartHtml",
    "wellbeingChartSvg",
    "wellbeingScore",
    "wellbeingScorePoints",
)

# HA-Theme-Variablen, aus denen das Chart seine Farben zieht.
_HA_THEME_VARS = (
    "--primary-color",
    "--card-background-color",
    "--divider-color",
    "--secondary-text-color",
)


def _panel_base_source() -> str:
    return (_WWW_DIR / "health-o-mat-panel-base.js").read_text(encoding="utf-8")


def _panel_views_source() -> str:
    return (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")


def _wellbeing_chart_css(text: str) -> str:
    """CSS-Regeln des Wohlbefinden-Charts (`.wb-chart …`) aus dem Basis-Modul."""
    return "\n".join(re.findall(r"\.wb-chart[^{]*\{[^}]*\}", text))


def test_panel_base_exposes_wellbeing_chart_helpers():
    """[REQ-HOM-112] Die Chart-Helper liegen im Basis-Modul (geteilte Logik)."""
    text = _panel_base_source()

    for name in _WELLBEING_CHART_HELPERS:
        assert re.search(rf"(?:export\s+)?function\s+{name}\s*\(", text), (
            f"{name}() fehlt im Panel-Basis-Modul"
        )


def test_panel_base_wellbeing_score_scale_constants():
    """[REQ-HOM-112] Skalenkonstanten: Minimum 1, Maximum = Anzahl der Zustände."""
    text = _panel_base_source()

    assert re.search(r"WELLBEING_SCORE_MIN\s*=\s*1\b", text), (
        "WELLBEING_SCORE_MIN (1) fehlt im Panel-Basis-Modul"
    )
    assert re.search(r"WELLBEING_SCORE_MAX\s*=\s*WELLBEING_STATES\.length", text), (
        "WELLBEING_SCORE_MAX folgt nicht der Zustandsliste"
    )


def test_panel_base_wellbeing_chart_is_accessible():
    """[REQ-HOM-112] SVG mit role="img" + aria-label, Datenpunkte mit <title>."""
    text = _panel_base_source()

    assert 'role="img"' in text
    assert "aria-label" in text
    assert "<title>" in text


def test_panel_base_wellbeing_chart_has_empty_state_hint():
    """[REQ-HOM-112] Leerfall: verständlicher Hinweis statt eines leeren Charts."""
    text = _panel_base_source()

    assert "Noch keine Wohlbefinden-Meldung" in text


def test_panel_base_wellbeing_chart_uses_ha_theme_variables():
    """[REQ-HOM-112] Die Chart-Farben kommen aus den HA-CSS-Variablen.

    Geprüft wird das CSS des Wohlbefinden-Charts (`.wb-chart …`) selbst —
    nicht die ganze Datei: eine Theme-Variable, die nur an anderer Stelle
    vorkommt, würde das dunkle HA-Theme des Charts nicht treffen.
    """
    chart_css = _wellbeing_chart_css(_panel_base_source())

    assert chart_css, "Chart-CSS (.wb-chart) fehlt im Panel-Basis-Modul"
    for var in _HA_THEME_VARS:
        assert f"var({var}" in chart_css, (
            f"HA-Theme-Variable {var} wird im Chart-CSS nicht verwendet"
        )


def test_panel_views_renders_wellbeing_chart_in_wellbeing_tab():
    """[REQ-HOM-112] Der Wohlbefinden-Tab rendert den Score-Chart."""
    views = _panel_views_source()

    assert re.search(r"import\s*\{[^}]*wellbeingChartHtml", views, re.S), (
        "wellbeingChartHtml wird nicht aus dem Basis-Modul importiert"
    )
    assert "function wellbeingTab" in views
    # Der Chart-Aufruf muss IM Wohlbefinden-Tab stehen (nach dessen Definition).
    assert views.index("wellbeingChartHtml(") > views.index("function wellbeingTab")


def test_panel_views_shows_wellbeing_score():
    """[REQ-HOM-112] Der Wohlbefinden-Tab zeigt den Score (Live-Entity oder Payload)."""
    views = _panel_views_source()

    assert "wellbeingScore" in views
    assert "wellbeing_score" in views  # logischer Entity-Schlüssel
    assert "WELLBEING_SCORE_MAX" in views


def test_panel_base_wellbeing_chart_marks_current_value_and_axis_extremes():
    """[REQ-HOM-112] Aktueller Wert und Achsen-Extremwerte sind hervorgehoben."""
    text = _panel_base_source()
    chart_css = _wellbeing_chart_css(text)

    # Styling für den hervorgehobenen aktuellen Punkt …
    assert ".wb-chart .point-current" in chart_css
    assert ".wb-chart .axis-extreme" in chart_css
    # … und dessen Verwendung im SVG (letzter Punkt) bzw. für die Extremwerte.
    assert re.search(r'"point point-current"', text)
    assert "axis-extreme" in text


def test_panel_base_wellbeing_chart_has_time_axis():
    """[REQ-HOM-112] Der Chart besitzt eine Zeitachse (Datum statt Index)."""
    text = _panel_base_source()

    assert re.search(r"function\s+formatChartDate\s*\(", text), (
        "formatChartDate() fehlt im Panel-Basis-Modul"
    )
    assert "axis-text" in text


# --- REQ-HOM-112: Quelltext-Assertions zur Series-Logik ----------------------
#
# Die Historie führt vergangene Meldungen (siehe `store.set_wellbeing`): ein
# Eintrag bedeutet "dieser Status wurde zu diesem Zeitpunkt gemeldet", der
# AKTUELLE Zustand steht ausschliesslich im `wellbeing`-Block. Ohne den
# aktuellen Punkt markiert der Chart den abgeloesten Wert als "aktuell"
# (Kopfzeile und Chart widersprechen sich). Die folgenden Assertions sichern
# genau diese Verknuepfung.


def _js_function_block(text: str, name: str) -> str:
    """Quelltext des Funktionsrumpfs von `name` (bis zur Zeile `}` auf Spalte 0)."""
    match = re.search(rf"function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", text)
    assert match is not None, f"{name}() fehlt im Quelltext"
    end = text.find("\n}", match.end())
    assert end != -1, f"{name}() hat keinen abschliessenden Block"
    return text[match.end() : end]


def test_req_hom_112_panel_base_exports_wellbeing_series_with_current_point():
    """[REQ-HOM-112] Das Basis-Modul exportiert die Series-Logik (Historie + aktuell)."""
    text = _panel_base_source()

    assert re.search(r"export\s+function\s+wellbeingSeries\s*\(", text), (
        "wellbeingSeries() wird nicht aus dem Panel-Basis-Modul exportiert"
    )
    body = _js_function_block(text, "wellbeingSeries")

    # Die Serie beginnt mit der Historie …
    assert "wellbeingScorePoints(history)" in body, "die Serie startet nicht mit der Historie"
    # … und haengt den aktuellen Wert an (aufgeloester Score, Zeitstempel).
    push = re.search(r"points\.push\(\s*\{(?P<fields>.*?)\}\s*\)\s*;", body, re.S)
    assert push is not None, "der aktuelle Wert wird nicht an die Serie angehaengt"
    fields = push.group("fields")
    assert re.search(r"\bscore\b", fields), "der angehaengte Punkt traegt keinen Score"
    assert re.search(r"\bts\b", fields), "der angehaengte Punkt traegt keinen Zeitstempel"

    # Ohne verwertbaren aktuellen Score bleibt die Serie = Historie.
    assert re.search(r"if\s*\(\s*score\s*={2,3}\s*null\s*\)\s*return\s+points\s*;", body), (
        "ohne aktuellen Score muss die Serie der Historie entsprechen"
    )


def test_req_hom_112_panel_views_passes_current_wellbeing_block_to_chart():
    """[REQ-HOM-112] Der Wohlbefinden-Tab reicht den aktuellen Block an den Chart.

    Ohne `current` wuerde der Chart den abgeloesten Historienwert als
    "aktuell" markieren — der Fix muss also Views-seitig wirksam sein.
    """
    views = _panel_views_source()

    match = re.search(r"wellbeingChartHtml\(\s*history\s*,\s*\{(?P<opts>.*?)\}\s*\)", views, re.S)
    assert match is not None, "wellbeingChartHtml wird nicht mit der Historie aufgerufen"
    opts = match.group("opts")
    assert re.search(r"\bcurrent\s*:", opts), "der aktuelle Block wird nicht durchgereicht"
    assert "data.wellbeing" in opts, "der aktuelle Block wird nicht aus dem Payload gelesen"

    # Der Aufruf muss im Wohlbefinden-Tab stehen (nicht in einem anderen Tab).
    assert match.start() > views.index("function wellbeingTab")


def test_req_hom_112_panel_base_chart_summary_uses_current_series_point():
    """[REQ-HOM-112] aria-label/Kopfzeile nennen den Score des LETZTEN Serienpunkts.

    Weil `wellbeingSeries` den aktuellen Wert als letzten Punkt anhaengt, ist
    der letzte Serienpunkt der aktuelle Wert — nicht der abgeloeste
    Historienpunkt.
    """
    text = _panel_base_source()

    assert re.search(r"const\s+last\s*=\s*list\[\s*list\.length\s*-\s*1\s*\]", text), (
        "die Zusammenfassung nutzt nicht den letzten Serienpunkt"
    )
    assert re.search(r"aktuell \$\{[^}]*score[^}]*\}", text), (
        "die Zusammenfassung nennt keinen aktuellen Score"
    )
    # Die Chart-Card holt ihre Punkte aus der Series (inkl. aktuellem Punkt).
    html_body = _js_function_block(text, "wellbeingChartHtml")
    assert re.search(r"wellbeingSeries\(\s*history\s*,\s*options\.current\s*\)", html_body), (
        "die Chart-Card haengt den aktuellen Block nicht an die Serie"
    )


# --- REQ-HOM-112: Verhaltenstest des Panel-Basis-Moduls (Node) ---------------
#
# Der Chart-Bug (REQ-HOM-112) ist nur mit echten Payloads sicher erkennbar:
# die Quelltext-Assertions oben koennten eine falsche Verdrahtung uebersehen.
# Darum wird das echte ES-Modul mit Node gerendert und das Ergebnis (Serie,
# `point-current`-Marker, aria-label, SVG) geprueft.
#
# Node ist OPTIONAL: in CI ohne `node` ueberspringt `skipif` die Tests sauber
# (nie rot wegen eines Import-/Aufruffehlers). Die Quelltext-Assertions oben
# sichern dieselben Invarianten unabhaengig von Node.

# Node-Runner: laedt das Basis-Modul als ES-Modul und rendert die Chart-Cases.
_NODE_RUNNER = """import { pathToFileURL } from "node:url";

const moduleUrl = pathToFileURL(process.argv[2]).href;
const mod = await import(moduleUrl);
const cases = JSON.parse(process.argv[3]);
const rendered = cases.map((testCase) => {
  const current = testCase.current === undefined ? null : testCase.current;
  return {
    series: mod.wellbeingSeries(testCase.history, current),
    html: mod.wellbeingChartHtml(testCase.history, {
      current,
      title: testCase.title || "Score-Verlauf",
    }),
  };
});
process.stdout.write(JSON.stringify(rendered));
"""

# Leermarken des Leerfalls (muss im gerenderten Chart-Block auftauchen).
_EMPTY_HINT = "Noch keine Wohlbefinden-Meldung"

# Payload A — der E2E-Fall: der letzte Historieneintrag traegt den abgeloesten
# Wert (Score 2), der aktuelle Wert ist Score 4 (gleicher Zeitstempel).
_HISTORY_A = [
    {"ts": "2026-10-17T08:00:00+02:00", "key": "very_bad", "score": 1},
    {"ts": "2026-10-17T20:00:00+02:00", "key": "okay", "score": 3},
    {"ts": "2026-10-18T08:00:00+02:00", "key": "bad", "score": 2},
    {"ts": "2026-10-18T20:00:00+02:00", "key": "great", "score": 5},
    {"ts": "2026-10-19T08:00:00+02:00", "key": "very_bad", "score": 1},
    {"ts": "2026-10-19T18:00:00+02:00", "key": "bad", "score": 2},
]
_CURRENT_A = {
    "key": "good",
    "label": "Gut",
    "emoji": "\U0001f642",
    "score": 4,
    "at": "2026-10-19T18:00:00+02:00",
}

# Payload B — genau eine Meldung (leere Historie, aktueller Wert vorhanden).
_CURRENT_B = {"key": "okay", "score": 3, "at": "2026-10-19T18:00:00+02:00"}

# Payload D — aelterer Payload ohne `score`-Feld: der Score wird aus dem Key
# abgeleitet (Index + 1 in aufsteigender Qualitaet).
_HISTORY_D = [
    {"ts": "2026-10-18T08:00:00+02:00", "key": "bad"},
    {"ts": "2026-10-18T20:00:00+02:00", "key": "great"},
]
_CURRENT_D = {"key": "good", "at": "2026-10-19T18:00:00+02:00"}


def _render_with_node(tmp_path, cases: list[dict]) -> list[dict]:
    """Rendert die Chart-Cases mit Node und liefert Serie + HTML je Case."""
    module_path = tmp_path / "health-o-mat-panel-base.mjs"
    # Byte-identische Kopie: Node stuft `.js` ohne package.json (type: module)
    # als CommonJS ein. Die Datei hat selbst keine Importe und keine
    # DOM-Abhaengigkeit (siehe Dateikopf) — die Kopie aendert das Verhalten
    # also nicht. Die `?v=<version>`-Query steckt nur in den Import-Specifiern
    # der ANDEREN Panel-Module; die Base-Datei wird ohne Query geladen.
    module_path.write_bytes((_WWW_DIR / "health-o-mat-panel-base.js").read_bytes())
    runner_path = tmp_path / "runner.mjs"
    runner_path.write_text(_NODE_RUNNER, encoding="utf-8")

    node = shutil.which("node") or "node"
    result = subprocess.run(
        [node, str(runner_path), str(module_path), json.dumps(cases)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"Node-Render des Panel-Basis-Moduls fehlgeschlagen (rc={result.returncode}): "
        f"{result.stderr}"
    )
    return json.loads(result.stdout)


def _svg_of(html: str) -> str:
    """Das gerenderte SVG aus dem Chart-HTML (ohne den umgebenden Card-Div)."""
    start = html.find("<svg")
    assert start != -1, "das gerenderte Chart enthaelt kein SVG"
    end = html.find("</svg>", start)
    assert end != -1, "das gerenderte SVG ist nicht geschlossen"
    return html[start : end + len("</svg>")]


def _chart_points(svg: str) -> list[dict]:
    """Datenpunkte des SVG: CSS-Klasse, Score (aus der Hoehe) und Tooltip-Text.

    Der Score wird aus der Y-Position abgeleitet: das SVG zeichnet die
    Gridlines der Skala 1…N mit den passenden Achsenbeschriftungen, der Punkt
    liegt exakt auf der Gridline seines Scores.
    """
    root = ET.fromstring(svg)
    grid_y: list[str] = []
    labels: list[str] = []
    for element in root.iter():
        if element.tag == "line" and (element.get("class") or "") == "grid-line":
            grid_y.append(element.get("y1"))
        elif element.tag == "text":
            labels.append((element.text or "").strip())
    score_by_y = dict(zip(grid_y, labels[: len(grid_y)], strict=False))

    points = []
    for circle in root.iter("circle"):
        title = circle.find("title")
        points.append(
            {
                "cls": circle.get("class") or "",
                "score": score_by_y.get(circle.get("cy")),
                "title": (title.text or "") if title is not None else "",
            }
        )
    return points


def _aria_label(svg: str) -> str:
    """aria-label des gerenderten SVG."""
    return ET.fromstring(svg).get("aria-label") or ""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_panel_chart_series_ends_with_current_score(tmp_path):
    """[REQ-HOM-112] Die Chart-Serie endet mit dem AKTUELLEN Score.

    E2E-Fall: der letzte Historieneintrag traegt den abgeloesten Wert
    (Score 2), der aktuelle Wert ist Score 4 (gleicher Zeitstempel). Der
    `point-current`-Marker und die aria-label muessen den aktuellen Wert
    nennen — nicht den abgeloesten.
    """
    rendered = _render_with_node(tmp_path, [{"history": _HISTORY_A, "current": _CURRENT_A}])[0]

    series = rendered["series"]
    assert len(series) == len(_HISTORY_A) + 1, "der aktuelle Punkt fehlt in der Serie"
    assert series[-1]["score"] == 4, "die Serie endet nicht mit dem aktuellen Score"
    assert series[-2]["score"] == 2, "der abgeloeste Historienwert fehlt in der Serie"

    html = rendered["html"]
    assert _EMPTY_HINT not in html, "der Chart zeigt trotz Meldungen den Leerfall-Hinweis"

    svg = _svg_of(html)
    points = _chart_points(svg)
    current_points = [point for point in points if "point-current" in point["cls"]]
    assert len(current_points) == 1, "es muss genau einen `point-current`-Marker geben"
    assert current_points[0]["score"] == "4", (
        "der `point-current`-Marker sitzt nicht auf dem Punkt mit dem aktuellen Score"
    )
    assert "(4 / 10)" in current_points[0]["title"], (
        "der Tooltip des aktuellen Punkts nennt nicht den aktuellen Score"
    )

    # Der abgeloeste Wert (Score 2) darf NICHT als aktuell markiert sein.
    stale = [point for point in points if point["score"] == "2"]
    assert stale, "der abgeloeste Punkt (Score 2) fehlt im Chart"
    assert all("point-current" not in point["cls"] for point in stale), (
        "der abgeloeste Wert wurde als aktueller Wert markiert"
    )

    label = _aria_label(svg)
    assert "aktuell 4 von 10" in label, "die aria-label nennt nicht den aktuellen Score"
    assert "aktuell 2 von 10" not in label, "die aria-label nennt den abgeloesten Score"


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_panel_chart_renders_single_current_report_without_history(tmp_path):
    """[REQ-HOM-112] Genau eine Meldung: der Chart zeigt genau einen Punkt."""
    rendered = _render_with_node(tmp_path, [{"history": [], "current": _CURRENT_B}])[0]

    series = rendered["series"]
    assert len(series) == 1, "aus einer Meldung entsteht nicht genau ein Punkt"
    assert series[0]["score"] == 3

    html = rendered["html"]
    assert _EMPTY_HINT not in html, "der Chart zeigt trotz Meldung den Leerfall-Hinweis"

    svg = _svg_of(html)
    points = _chart_points(svg)
    assert len(points) == 1, "das SVG zeigt nicht genau einen Datenpunkt"
    assert points[0]["score"] == "3"
    assert "point-current" in points[0]["cls"], "der einzige Punkt ist nicht als aktuell markiert"
    assert "aktuell 3 von 10" in _aria_label(svg)


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_panel_chart_shows_empty_hint_without_any_report(tmp_path):
    """[REQ-HOM-112] Ohne Meldung: Hinweis statt eines leeren/kaputten SVG."""
    rendered = _render_with_node(tmp_path, [{"history": [], "current": None}])[0]

    assert rendered["series"] == []
    html = rendered["html"]
    assert _EMPTY_HINT in html, "der Leerfall-Hinweis fehlt"
    assert "<svg" not in html, "im Leerfall wird ein (leeres) SVG gerendert"


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_panel_chart_derives_score_from_key_for_legacy_payloads(tmp_path):
    """[REQ-HOM-112] Aeltere Payloads ohne `score`: Score wird aus dem Key abgeleitet."""
    rendered = _render_with_node(tmp_path, [{"history": _HISTORY_D, "current": _CURRENT_D}])[0]

    series = rendered["series"]
    assert [point["score"] for point in series] == [3, 9, 7], (
        "der Score wurde nicht aus dem Zustands-Key abgeleitet"
    )

    svg = _svg_of(rendered["html"])
    assert "aktuell 7 von 10" in _aria_label(svg), (
        "die aria-label nennt nicht den abgeleiteten aktuellen Score"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_panel_chart_avoids_duplicate_point_for_identical_current(tmp_path):
    """[REQ-HOM-112] Duplikat-Regel: gleicher Zeitstempel + gleicher Score -> kein
    zusaetzlicher Punkt; gleicher Zeitstempel + anderer Score -> angehaengt.
    """
    ts = "2026-10-19T18:00:00+02:00"
    identical = {
        "history": [{"ts": ts, "key": "good", "score": 4}],
        "current": {"key": "good", "score": 4, "at": ts},
    }
    changed = {
        "history": [{"ts": ts, "key": "bad", "score": 2}],
        "current": {"key": "good", "score": 4, "at": ts},
    }

    rendered = _render_with_node(tmp_path, [identical, changed])

    assert len(rendered[0]["series"]) == 1, "der identische aktuelle Wert verdoppelt den Punkt"
    assert rendered[0]["series"][0]["score"] == 4
    assert len(rendered[1]["series"]) == 2, "der geaenderte aktuelle Wert wurde nicht angehaengt"
    assert rendered[1]["series"][-1]["score"] == 4


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_panel_chart_svg_is_valid_xml_without_invalid_numbers(tmp_path):
    """[REQ-HOM-112] Das gerenderte SVG ist wohlgeformtes XML ohne NaN/undefined."""
    cases = [
        {"history": _HISTORY_A, "current": _CURRENT_A},
        {"history": [], "current": _CURRENT_B},
        {"history": _HISTORY_D, "current": _CURRENT_D},
    ]

    for rendered in _render_with_node(tmp_path, cases):
        svg = _svg_of(rendered["html"])
        for invalid in ("NaN", "undefined", "Infinity"):
            assert invalid not in svg, f"das SVG enthaelt den ungueltigen Wert {invalid!r}"
        try:
            ET.fromstring(svg)
        except ET.ParseError as err:  # pragma: no cover - nur bei defektem SVG
            pytest.fail(f"das gerenderte SVG ist kein wohlgeformtes XML: {err}\n{svg}")


# --- REQ-HOM-112: Score-Aufloesungsregel (identisch in Card und Panel) ------
#
# Die Aufloesungsregel (der Server ist die Wahrheit):
#   1. Ist das Feld `score` im Objekt VORHANDEN (auch bei `null`), gilt der
#      Server-Wert — `null`/nicht-numerisch bedeutet: KEIN Score. Es wird
#      KEIN clientseitiger Ersatzwert abgeleitet (zwei Wahrheiten sind ein
#      Widerspruch, kein Feature).
#   2. FEHLT das Feld `score` komplett (aelterer Server), wird der Score aus
#      dem kanonischen Key abgeleitet — EXAKT und case-sensitiv (Index + 1),
#      identisch zu `logic.wellbeing_score`.
#   3. Der Score muss im Bereich 1..N liegen (nie 0).
#
# Card und Panel muessen fuer denselben Input denselben Score liefern — die
# Regel ist an beiden Stellen dupliziert (die Karte ist ein eigenstaendiges
# Skript ohne Imports) und muss deshalb gegen beide Implementierungen
# geprueft werden.

# (Eingabe, erwarteter Score) — die Ausgabe ist `null` (kein Score) oder 1..N.
_SCORE_RULE_CASES = [
    pytest.param({"score": 4, "key": "good"}, 4, id="server-score-wins"),
    pytest.param({"score": None, "key": "good"}, None, id="server-null-is-truth"),
    pytest.param({"key": "good"}, 7, id="legacy-derivation-from-key"),
    pytest.param({"key": "bogus_stage"}, None, id="no-key-alias-table"),
    pytest.param({"key": "GOOD"}, None, id="exact-case-sensitive-match"),
    pytest.param({"score": 0, "key": "good"}, None, id="never-zero"),
    pytest.param({"score": 11, "key": "good"}, None, id="outside-scale"),
    # Nicht-String-Keys: `key: null`, `key: ""` und `key: 123` sind KEIN
    # verwertbarer Key -> kein Score (die Python-Seite deckt das bereits ab;
    # die JS-Regeltabelle muss es mitfuehren, sonst driftet die Tabelle).
    pytest.param({"key": None}, None, id="null-key"),
    pytest.param({"key": ""}, None, id="empty-key"),
    pytest.param({"key": 123}, None, id="non-string-key"),
]

# Node-Runner: laedt das Panel-Basis-Modul als ES-Modul und ruft die
# Score-Aufloesung je Case auf. Die Basis-Datei hat selbst keine Importe —
# sie wird deshalb direkt (ohne `?v=`-Query) geladen.
_NODE_SCORE_RUNNER = """import { pathToFileURL } from "node:url";

const moduleUrl = pathToFileURL(process.argv[2]).href;
const mod = await import(moduleUrl);
const cases = JSON.parse(process.argv[3]);
const scores = cases.map((raw) => mod.wellbeingScore(raw));
process.stdout.write(JSON.stringify(scores));
"""

# Node-Runner: laedt die Karte als klassisches Script in einen `vm`-Context
# mit DOM-Stubs. Im `vm`-Script werden Top-Level-Funktionsdeklarationen zu
# Eigenschaften des Context-Globals (`ctx.wellbeingScore(...)`); die
# `const`-Spiegel (`WELLBEING_SCALE`) bleiben lexikalisch gebunden — das ist
# gewollt (der Mirror wird separat gepinnt, siehe tests/test_logic.py).
_NODE_CARD_SCORE_RUNNER = """import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");
const cases = JSON.parse(process.argv[3]);

/* DOM-Stubs: die Karte registriert sich beim Laden (customElements.define)
 * und nutzt `window.customCards`; fuer die Score-Logik genuegen diese
 * Stubs. */
const context = {
  HTMLElement: class HTMLElement {},
  customElements: { get: () => undefined, define: () => {} },
  window: {},
  document: { createElement: () => ({}) },
  console: { info: () => {}, log: () => {}, warn: () => {}, error: () => {} },
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "health-o-mat-card.js" });

const scores = cases.map((raw) => context.wellbeingScore(raw));
process.stdout.write(JSON.stringify(scores));
"""


def _run_node(tmp_path, runner_source: str, args: list[str], name: str) -> str:
    """Fuehrt einen Node-Runner aus und liefert dessen stdout."""
    runner_path = tmp_path / f"{name}.mjs"
    runner_path.write_text(runner_source, encoding="utf-8")

    node = shutil.which("node") or "node"
    result = subprocess.run(
        [node, str(runner_path), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"Node-Runner {name} fehlgeschlagen (rc={result.returncode}): {result.stderr}"
    )
    return result.stdout


def _panel_base_module(tmp_path) -> Path:
    """Das Panel-Basis-Modul als ES-Modul (byte-identische Kopie)."""
    module_path = tmp_path / "health-o-mat-panel-base.mjs"
    module_path.write_bytes((_WWW_DIR / "health-o-mat-panel-base.js").read_bytes())
    return module_path


def _card_module(tmp_path) -> Path:
    """Die Karte als Skript-Datei (byte-identische Kopie)."""
    module_path = tmp_path / "health-o-mat-card.js"
    module_path.write_bytes((_WWW_DIR / "health-o-mat-card.js").read_bytes())
    return module_path


def _panel_scores(tmp_path, cases: list[dict]) -> list:
    """Score-Aufloesung des Panel-Basis-Moduls je Case."""
    module_path = _panel_base_module(tmp_path)
    out = _run_node(
        tmp_path, _NODE_SCORE_RUNNER, [str(module_path), json.dumps(cases)], "runner_panel_score"
    )
    return json.loads(out)


def _card_scores(tmp_path, cases: list[dict]) -> list:
    """Score-Aufloesung der Karte je Case."""
    module_path = _card_module(tmp_path)
    out = _run_node(
        tmp_path,
        _NODE_CARD_SCORE_RUNNER,
        [str(module_path), json.dumps(cases)],
        "runner_card_score",
    )
    return json.loads(out)


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
@pytest.mark.parametrize(("raw", "expected"), _SCORE_RULE_CASES)
def test_req_hom_112_panel_base_wellbeing_score_follows_server_truth_rule(tmp_path, raw, expected):
    """[REQ-HOM-112] Panel: der Server ist die Wahrheit, sonst exakte Ableitung."""
    scores = _panel_scores(tmp_path, [raw])

    assert scores == [expected], (
        f"das Panel loest {raw!r} zu {scores[0]!r} auf, erwartet {expected!r}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
@pytest.mark.parametrize(("raw", "expected"), _SCORE_RULE_CASES)
def test_req_hom_112_card_wellbeing_score_follows_server_truth_rule(tmp_path, raw, expected):
    """[REQ-HOM-112] Karte: dieselbe Regel wie im Panel (Server ist die Wahrheit)."""
    scores = _card_scores(tmp_path, [raw])

    assert scores == [expected], (
        f"die Karte loest {raw!r} zu {scores[0]!r} auf, erwartet {expected!r}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_card_and_panel_resolve_the_same_wellbeing_score(tmp_path):
    """[REQ-HOM-112] Card und Panel liefern fuer denselben Input denselben Score.

    Die Regel ist in beiden Frontends dupliziert (die Karte ist ein
    eigenstaendiges Skript ohne Imports) — eine Divergenz wuerde im Panel
    "4 / 10" und in der Karte "2 / 10" anzeigen.
    """
    cases = [case.values[0] for case in _SCORE_RULE_CASES]

    panel_scores = _panel_scores(tmp_path, cases)
    card_scores = _card_scores(tmp_path, cases)

    assert panel_scores == card_scores, (
        f"Card und Panel liefern unterschiedliche Scores: {card_scores} != {panel_scores}"
    )
    # Kontrollfall: die erwarteten Werte sind tatsaechlich gemessen (nicht nur
    # "beide gleich" — ein leeres Resultat waere ein "always green"-Test).
    assert panel_scores == [case.values[1] for case in _SCORE_RULE_CASES]


# --- REQ-HOM-112: Panel-Konsistenz (Kopfzeile und Chart) --------------------
#
# Der `panel_data`-Snapshot kann veraltet sein (die Meldung kam von ausserhalb
# des Panels: Select-Entity, Automation, Dashboard). Der Score kommt dann aus
# der Live-Entity (`wellbeing_score`), der Payload traegt noch den alten Wert.
# Kopfzeile und Chart muessen denselben Score zeigen — sonst zeigt das Panel
# "2 / 10" in der Kopfzeile und markiert im Chart den Wert 4 als aktuell (oder
# umgekehrt).

# Node-Runner: rendert den Wohlbefinden-Tab ueber die oeffentliche
# `renderDetail()`-Funktion (der Tab wird ueber `panel._tab` gewaehlt) und
# liefert das gerenderte HTML.
_NODE_VIEWS_RUNNER = """import { pathToFileURL } from "node:url";

const mod = await import(pathToFileURL(process.argv[2]).href);
const spec = JSON.parse(process.argv[3]);

const entryId = spec.entry_id;
const panel = {
  _selectedEntry: entryId,
  _persons: [{ entry_id: entryId, display_name: spec.display_name }],
  _data: { [entryId]: spec.data },
  _entryErrors: {},
  _tab: "wellbeing",
  _actionError: "",
  _busy: false,
  _liveValue: (data, key, fallback) => (key === "wellbeing" ? spec.live_wellbeing : fallback),
  _liveNumber: (data, key, fallback) => (key === "wellbeing_score" ? spec.live_score : fallback),
};
const html = mod.renderDetail(panel);
process.stdout.write(JSON.stringify({ html }));
"""

# Payload mit VERALTETEM Snapshot: `wellbeing.score` = 2, die Live-Entity
# `wellbeing_score` liefert 4. Die Historie enthaelt nur den Wert 1, damit
# die alte 2 nirgends im gerenderten Panel auftauchen kann.
_PANEL_STALE_SNAPSHOT = {
    "goal_ml": 2000,
    "areas": {"drink": True, "bp": True, "wellbeing": True},
    "wellbeing": {
        "key": "bad",
        "label": "Schlecht",
        "emoji": "\U0001f641",
        "at": "2026-10-19T18:00:00+02:00",
        "score": 2,
        "history": [
            {
                "ts": "2026-10-19T08:00:00+02:00",
                "key": "very_bad",
                "label": "Sehr schlecht",
                "emoji": "\U0001f635",
                "score": 1,
            }
        ],
    },
}


def _prepare_views_copy(tmp_path) -> Path:
    """Kopien der Views-/Basis-Module ohne `?v=`-Query (Node-ESM-tauglich).

    `panel-views.js` importiert das Basis-Modul mit der Cache-Buster-Query
    (`?v=0.8.0`) — die Query bricht die Node-ESM-Aufloesung (unbekannter
    Dateiname). Im Test-Verzeichnis wird die Query entfernt; die Kopien sind
    byte-identisch (ausser dem Import-Specifier) und aendern das Verhalten
    nicht.
    """
    views_source = (_WWW_DIR / "health-o-mat-panel-views.js").read_text(encoding="utf-8")
    patched, count = re.subn(
        r'"\./health-o-mat-panel-base\.js\?v=[^"]+"',
        '"./health-o-mat-panel-base.js"',
        views_source,
    )
    assert count == 1, "der Import-Specifier des Basis-Moduls wurde nicht gefunden"

    (tmp_path / "health-o-mat-panel-views.js").write_text(patched, encoding="utf-8")
    (tmp_path / "health-o-mat-panel-base.js").write_bytes(
        (_WWW_DIR / "health-o-mat-panel-base.js").read_bytes()
    )
    # Ohne package.json stuft Node `.js` als CommonJS ein — die Kopien sollen
    # ES-Module bleiben (wie im Browser).
    (tmp_path / "package.json").write_text(json.dumps({"type": "module"}), encoding="utf-8")
    return tmp_path / "health-o-mat-panel-views.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_panel_wellbeing_tab_shows_live_score_in_header_and_chart(tmp_path):
    """[REQ-HOM-112] Kopfzeile und Chart zeigen denselben (Live-)Score.

    Der `panel_data`-Snapshot traegt den veralteten Score 2, die Live-Entity
    `wellbeing_score` liefert 4. Beide Anzeigen muessen 4 zeigen.
    """
    views_copy = _prepare_views_copy(tmp_path)
    spec = {
        "entry_id": "entry-1",
        "display_name": "Alex",
        "live_wellbeing": "unknown",
        "live_score": 4,
        "data": _PANEL_STALE_SNAPSHOT,
    }

    out = json.loads(
        _run_node(
            tmp_path, _NODE_VIEWS_RUNNER, [str(views_copy), json.dumps(spec)], "runner_panel_views"
        )
    )
    html = out["html"]

    # (a) Kopfzeile: "Zuletzt: … · 4 / 5" — nicht der veraltete Wert 2.
    header = re.search(r"Zuletzt:.*?</span>", html, re.S)
    assert header is not None, "die Kopfzeile des Wohlbefinden-Tabs fehlt"
    header_html = header.group(0)
    assert "4 / 10" in header_html, f"die Kopfzeile zeigt nicht den Live-Score: {header_html}"
    assert "2 / 10" not in header_html, f"die Kopfzeile zeigt den veralteten Score: {header_html}"

    # (b) Chart: aria-label und `point-current` nennen denselben Wert 4.
    svg = _svg_of(html)
    assert "aktuell 4 von 10" in _aria_label(svg), (
        f"die aria-label nennt nicht den Live-Score: {_aria_label(svg)}"
    )
    assert "aktuell 2 von 10" not in _aria_label(svg), (
        f"die aria-label nennt den veralteten Score: {_aria_label(svg)}"
    )

    points = _chart_points(svg)
    current_points = [point for point in points if "point-current" in point["cls"]]
    assert len(current_points) == 1, "es muss genau einen `point-current`-Marker geben"
    assert current_points[0]["score"] == "4", (
        f"der `point-current`-Marker sitzt nicht auf dem Wert 4: {current_points[0]}"
    )

    # (c) Der veraltete Snapshot-Score taucht nirgends im Panel auf.
    assert "2 / 10" not in html, "der veraltete Snapshot-Score (2) wird noch angezeigt"


# --- REQ-HOM-112: Quelltext-Assertions zur Aufloesungsregel -----------------
#
# Die Alias-Tabelle (Card) ist entfernt: eine zweite Quelle fuer die
# Key->Score-Zuordnung waere eine zweite Wahrheit. Die Emoji-Tabelle ist
# NICHT Teil des Score-Pfads und muss erhalten bleiben.


def test_req_hom_112_no_wellbeing_key_alias_table_in_frontends():
    """[REQ-HOM-112] `WELLBEING_KEY_ALIASES` existiert in keinem Frontend mehr."""
    for name in ("health-o-mat-card.js", "health-o-mat-panel-base.js"):
        text = (_WWW_DIR / name).read_text(encoding="utf-8")
        assert "WELLBEING_KEY_ALIASES" not in text, (
            f"die Alias-Tabelle WELLBEING_KEY_ALIASES existiert noch in {name}"
        )
        # Auch keine anders benannte Alias-Tabelle: der Key muss exakt
        # gematcht werden (keine zweite Quelle fuer die Key->Score-Zuordnung).
        assert not re.search(r"WELLBEING\w*ALIAS\w*", text), (
            f"{name} enthaelt noch eine Alias-Tabelle fuer den Wohlbefinden-Key"
        )


def test_req_hom_112_wellbeing_emoji_table_still_present_in_card():
    """[REQ-HOM-112] Die Emoji-Tabelle der Karte bleibt erhalten.

    Die Emoji-Zuordnung ist nicht Teil des Score-Pfads (sie betrifft nur die
    Anzeige) — sie darf beim Umbau der Score-Aufloesung nicht versehentlich
    mitverschwinden.
    """
    text = (_WWW_DIR / "health-o-mat-card.js").read_text(encoding="utf-8")

    assert re.search(r"\bWELLBEING_EMOJI\s*=\s*\{", text), (
        "die Emoji-Tabelle WELLBEING_EMOJI fehlt in der Karte"
    )
    assert re.search(r"WELLBEING_EMOJI\s*\[\s*key\s*\]", text), (
        "die Emoji-Tabelle der Karte wird nicht mehr verwendet"
    )


# --- REQ-HOM-112: Marker-Semantik "aktuell" (isCurrent) ---------------------
#
# Der aktuelle Wert wird EXPLICIT markiert (`isCurrent: true`) — er ist der
# angehaengte aktuelle Punkt, NICHT der letzte Historienpunkt (per
# Store-Semantik ist der letzte Historieneintrag der ABGELOESTE Status).
#
# Ohne verwertbaren aktuellen Wert wird NICHTS hervorgehoben und die
# Zusammenfassung lautet "letzter Wert N von M" (nicht "aktuell N von M").
# Wichtig: der Fall ist "current VORHANDEN, aber ohne verwertbaren Score" —
# nicht "current fehlt komplett".
#
# Zusaetzlich: Label/Emoji werden LIVE-FIRST aufgeloest (Attribute der
# Live-Entity vor dem moeglicherweise veralteten WS-Snapshot).

# `current` VORHANDEN, aber `score: null` -> kein verwertbarer Score.
_CURRENT_WITHOUT_SCORE = {
    "key": "good",
    "label": "Gut",
    "emoji": "\U0001f642",
    "score": None,
    "at": "2026-10-19T18:00:00+02:00",
}


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_panel_chart_marks_exactly_one_current_point(tmp_path):
    """[REQ-HOM-112] Normalfall: genau EIN `point-current` = aktueller Score.

    Der letzte Historienpunkt (abgeloester Wert) darf abweichen — er wird
    gerade NICHT markiert.
    """
    rendered = _render_with_node(tmp_path, [{"history": _HISTORY_A, "current": _CURRENT_A}])[0]

    svg = _svg_of(rendered["html"])
    points = _chart_points(svg)
    current_points = [point for point in points if "point-current" in point["cls"]]

    assert len(current_points) == 1, (
        f"es muss genau einen `point-current`-Marker geben, gefunden: {len(current_points)}"
    )
    assert current_points[0]["score"] == str(_CURRENT_A["score"]), (
        "der `point-current`-Marker sitzt nicht auf dem aktuellen Score "
        f"(erwartet {_CURRENT_A['score']}, gefunden {current_points[0]['score']})"
    )
    assert f"({_CURRENT_A['score']} / 10)" in current_points[0]["title"], (
        f"der Tooltip des aktuellen Punkts nennt nicht den aktuellen Score: "
        f"{current_points[0]['title']!r}"
    )

    label = _aria_label(svg)
    assert f"aktuell {_CURRENT_A['score']} von 10" in label, (
        f"die aria-label nennt nicht den aktuellen Score: {label!r}"
    )

    # Der abgeloeste letzte Historienpunkt (Score 2) ist NICHT markiert.
    stale = [point for point in points if point["score"] == "2"]
    assert stale, "der abgeloeste Punkt (Score 2) fehlt im Chart"
    assert all("point-current" not in point["cls"] for point in stale), (
        "der abgeloeste Wert wurde als aktueller Wert markiert"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_panel_chart_without_current_score_marks_nothing(tmp_path):
    """[REQ-HOM-112] Restfall: `current` ohne Score -> KEIN `point-current`.

    Der `aria-label` sagt dann "letzter Wert N von M" und sagt **nicht**
    "aktuell" — der letzte Serienpunkt ist ein abgeloester Historienwert.
    """
    rendered = _render_with_node(
        tmp_path, [{"history": _HISTORY_A, "current": _CURRENT_WITHOUT_SCORE}]
    )[0]

    # Die Serie bleibt = Historie (kein aktueller Punkt angehaengt).
    series = rendered["series"]
    assert len(series) == len(_HISTORY_A), (
        f"ohne verwertbaren aktuellen Score darf kein Punkt angehaengt werden: {len(series)}"
    )
    assert all(point.get("isCurrent") is not True for point in series), (
        "ein Historienpunkt traegt den `isCurrent`-Marker"
    )

    html = rendered["html"]
    assert _EMPTY_HINT not in html, "der Chart zeigt trotz Meldungen den Leerfall-Hinweis"

    svg = _svg_of(html)
    points = _chart_points(svg)
    current_points = [point for point in points if "point-current" in point["cls"]]
    assert not current_points, (
        f"ohne aktuellen Wert darf kein Punkt hervorgehoben werden: {current_points}"
    )

    label = _aria_label(svg)
    assert "letzter Wert" in label, f"die aria-label nennt keinen letzten Wert: {label!r}"
    assert "aktuell" not in label, (
        f"die aria-label behauptet ohne aktuellen Wert einen aktuellen Wert: {label!r}"
    )
    # Der zuletzt gescorte Wert wird als "letzter Wert" genannt (Score 2).
    assert "letzter Wert 2 von 10" in label, f"die aria-label nennt den falschen Wert: {label!r}"


# Snapshot mit (bewusst veralteten) Label/Emoji.
_SNAPSHOT_LABEL = "Snapshot-Label"
_SNAPSHOT_EMOJI = "🅰"
_LIVE_LABEL = "Live-Label"
_LIVE_EMOJI = "🅱"


# Node-Runner: laedt die Karte als klassisches Script in einen `vm`-Context
# mit DOM-Stubs und rendert den Wohlbefinden-Block der Karte.
#
# Die Karte ist ein Web-Component: der relevante Code liegt in der Methode
# `_wellbeing()`. Deshalb wird die Klasse im `vm`-Kontext instanziiert und die
# Methode direkt aufgerufen (der Kontext bekommt `_config`, `_data` und
# `_hass` mit den echten Entity-Ids/States).
_NODE_CARD_WELLBEING_RUNNER = """import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(process.argv[2], "utf8");
const cases = JSON.parse(process.argv[3]);

/* DOM-Stubs: die Karte registriert sich beim Laden (customElements.define),
 * erbt von HTMLElement und nutzt `attachShadow`. */
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
  customElements: { get: () => undefined, define: () => {} },
  window: {},
  document: { createElement: () => ({}), addEventListener: () => {} },
  console: { info: () => {}, log: () => {}, warn: () => {}, error: () => {} },
  setTimeout: () => 0,
  clearTimeout: () => {},
  __spec: cases,
  __out: null,
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "health-o-mat-card.js" });

/* Die Auswertung laeuft IM vm-Kontext: `HealthOMatCard` ist dort eine
 * lexikalische Klassen-Bindung (kein Eigenschaft des globalen Objekts). */
vm.runInContext(
  `
  __out = __spec.map((testCase) => {
    const card = new HealthOMatCard();
    card._config = { entry_id: testCase.entry_id };
    card._data = testCase.data;
    card._hass = { states: testCase.states };
    const html = card._wellbeing();
    const score = null;
    return { html: html, score: score };
  });
  `,
  context,
  { filename: "card-wellbeing-probe.js" }
);

process.stdout.write(JSON.stringify(context.__out));
"""


def _card_wellbeing_html(tmp_path, cases: list[dict]) -> list[dict]:
    """Rendert den Wohlbefinden-Block der Karte je Case (Node + DOM-Stubs)."""
    module_path = _card_module(tmp_path)
    out = _run_node(
        tmp_path,
        _NODE_CARD_WELLBEING_RUNNER,
        [str(module_path), json.dumps(cases)],
        "runner_card_wellbeing",
    )
    return json.loads(out)


def _card_svg(html: str) -> str:
    """Das Sparkline-SVG aus dem gerenderten Karten-Block."""
    start = html.find("<svg")
    assert start != -1, "der gerenderte Karten-Block enthaelt kein SVG"
    end = html.find("</svg>", start)
    assert end != -1, "das gerenderte SVG ist nicht geschlossen"
    return html[start : end + len("</svg>")]


def _score_from_title(title: str) -> int | None:
    """Der Score aus dem Tooltip-Titel eines Punkts ("… (4 / 5)").

    Die Sparkline der Karte hat KEINE Achsenbeschriftung (anders als der
    Panel-Chart) — der Score steht deshalb nur im Tooltip.
    """
    match = re.search(r"\((\d+)\s*/\s*\d+\)\s*$", title or "")
    return int(match.group(1)) if match else None


def _card_entity_states(score: str | None, label: str | None, emoji: str | None) -> dict:
    """Live-States der Karten-Entities (Score-/Wohlbefinden-Sensor)."""
    attributes: dict = {}
    if label is not None:
        attributes["label"] = label
    if emoji is not None:
        attributes["emoji"] = emoji
    return {
        "sensor.hom_wellbeing_score": {
            "entity_id": "sensor.hom_wellbeing_score",
            "state": score if score is not None else "unknown",
            "attributes": {},
        },
        "sensor.hom_wellbeing_last_reported": {
            "entity_id": "sensor.hom_wellbeing_last_reported",
            "state": "2026-10-19T18:00:00+02:00",
            "attributes": attributes,
        },
    }


def _card_case(history: list[dict], current: dict, live_score: str | None) -> dict:
    """Ein Karten-Case: Snapshot-Block + Live-States.

    Der Snapshot traegt bewusst die veralteten Label-/Emoji-Werte — die
    Live-first-Aufloesung muss sie ueberholen.
    """
    wellbeing = dict(current)
    wellbeing["label"] = _SNAPSHOT_LABEL
    wellbeing["emoji"] = _SNAPSHOT_EMOJI
    wellbeing["history"] = history
    return {
        "entry_id": "entry-1",
        "data": {
            "person": "E2E",
            "areas": {"drink": False, "bp": False, "wellbeing": True},
            "entities": {
                "wellbeing": "sensor.hom_wellbeing_last_reported",
                "wellbeing_score": "sensor.hom_wellbeing_score",
            },
            "wellbeing": wellbeing,
        },
        "states": _card_entity_states(live_score, None, None),
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_card_without_current_score_has_no_badge_and_no_current_point(tmp_path):
    """[REQ-HOM-112] Card analog: ohne aktuellen Wert kein Badge, kein Marker.

    Die Sparkline behauptet dann keinen aktuellen Wert: kein `point-current`
    und die aria-label nennt "letzter Wert" (nicht "aktuell").
    """
    case = _card_case(_HISTORY_A, _CURRENT_WITHOUT_SCORE, None)
    rendered = _card_wellbeing_html(tmp_path, [case])[0]
    html = rendered["html"]

    assert 'class="score"' not in html, "ohne aktuellen Score wird ein Score-Badge gerendert"

    svg = _card_svg(html)
    points = _chart_points(svg)
    # Kontrollfall: die Historie IST gerendert (der Test ist nicht leer).
    assert len(points) == len(_HISTORY_A), (
        f"die Sparkline zeigt nicht die Historie: {len(points)} statt {len(_HISTORY_A)}"
    )
    current_points = [point for point in points if "point-current" in point["cls"]]
    assert not current_points, (
        f"ohne aktuellen Wert darf die Sparkline keinen Punkt hervorheben: {current_points}"
    )

    label = _aria_label(svg)
    assert "letzter Wert" in label, f"die aria-label nennt keinen letzten Wert: {label!r}"
    assert "aktuell" not in label, (
        f"die Sparkline behauptet ohne aktuellen Wert einen aktuellen Wert: {label!r}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_card_with_current_score_shows_badge_and_one_current_point(tmp_path):
    """[REQ-HOM-112] Card-Normalfall: Badge und Marker zeigen denselben Wert."""
    case = _card_case(_HISTORY_A, _CURRENT_A, str(_CURRENT_A["score"]))
    rendered = _card_wellbeing_html(tmp_path, [case])[0]
    html = rendered["html"]

    assert f'class="score">{_CURRENT_A["score"]} / 10<' in html, (
        f"das Score-Badge zeigt nicht den aktuellen Score: {html!r}"
    )

    svg = _card_svg(html)
    points = _chart_points(svg)
    current_points = [point for point in points if "point-current" in point["cls"]]
    assert len(current_points) == 1, (
        f"es muss genau einen `point-current`-Marker geben: {len(current_points)}"
    )
    assert _score_from_title(current_points[0]["title"]) == _CURRENT_A["score"], (
        f"der `point-current`-Marker sitzt nicht auf dem Badge-Wert: {current_points[0]!r}"
    )
    assert f"aktuell {_CURRENT_A['score']} von 10" in _aria_label(svg), (
        f"die aria-label nennt nicht den aktuellen Score: {_aria_label(svg)!r}"
    )


# --- REQ-HOM-112: Live-first-Aufloesung von Label/Emoji --------------------
#
# Der `panel_data`-Snapshot kann veraltet sein (die Meldung kam von ausserhalb
# des Panels: Select-Entity, Automation, Dashboard). Liefert die Live-Entity
# die Attribute `label`/`emoji`, sind diese aktueller als der Snapshot —
# sonst wuerde die Kopfzeile einen veralteten Text neben dem aktuellen Score
# zeigen. Ohne Live-Attribute bleibt der Snapshot die Quelle.

# Node-Runner: rendert den Wohlbefinden-Tab mit Live-Attributen. Der Panel-
# Stub beherrscht `_entityOf`/`_state` (Attributzugriff) und
# `_liveValue`/`_liveNumber` (Zustandswert).
_NODE_VIEWS_LIVE_RUNNER = """import { pathToFileURL } from "node:url";

const mod = await import(pathToFileURL(process.argv[2]).href);
const spec = JSON.parse(process.argv[3]);

const entryId = spec.entry_id;
const states = spec.states || {};
const panel = {
  _selectedEntry: entryId,
  _persons: [{ entry_id: entryId, display_name: spec.display_name }],
  _data: { [entryId]: spec.data },
  _entryErrors: {},
  _tab: "wellbeing",
  _actionError: "",
  _busy: false,
  _entityOf: (data, key) => ((data && data.entities) || {})[key] || "",
  _state: (entityId) => states[entityId],
  _stateValue: (entityId, fallback) => {
    const s = states[entityId];
    if (!s || s.state == null) return fallback;
    const v = s.state;
    if (v === "unknown" || v === "unavailable" || v === "") return fallback;
    return v;
  },
  _stateNumber: (entityId, fallback) => {
    const raw = panel._stateValue(entityId, undefined);
    if (raw === undefined) return fallback;
    const num = Number(raw);
    return Number.isFinite(num) ? num : fallback;
  },
  _liveValue: (data, key, fallback) => panel._stateValue(panel._entityOf(data, key), fallback),
  _liveNumber: (data, key, fallback) => panel._stateNumber(panel._entityOf(data, key), NaN) === NaN
    ? fallback
    : panel._stateNumber(panel._entityOf(data, key), NaN),
};
const html = mod.renderDetail(panel);
process.stdout.write(JSON.stringify({ html }));
"""

# Snapshot mit (bewusst veralteten) Label/Emoji.
_LIVE_SNAPSHOT = {
    "goal_ml": 800,
    "areas": {"drink": True, "bp": True, "wellbeing": True},
    "entities": {
        "wellbeing": "sensor.hom_wellbeing_last_reported",
        "wellbeing_score": "sensor.hom_wellbeing_score",
    },
    "wellbeing": {
        "key": "good",
        "label": _SNAPSHOT_LABEL,
        "emoji": _SNAPSHOT_EMOJI,
        "at": "2026-10-19T18:00:00+02:00",
        "score": 4,
        "history": [],
    },
}


def _live_states(with_attributes: bool) -> dict:
    """Live-States der Panel-Entities — mit oder ohne Label-/Emoji-Attribut."""
    attributes = {"label": _LIVE_LABEL, "emoji": _LIVE_EMOJI} if with_attributes else {}
    return {
        "sensor.hom_wellbeing_last_reported": {
            "entity_id": "sensor.hom_wellbeing_last_reported",
            "state": "2026-10-19T18:00:00+02:00",
            "attributes": attributes,
        },
        "sensor.hom_wellbeing_score": {
            "entity_id": "sensor.hom_wellbeing_score",
            "state": "4",
            "attributes": {},
        },
    }


def _render_views_with_live(tmp_path, states: dict) -> str:
    """Rendert den Wohlbefinden-Tab mit den angegebenen Live-States."""
    views_copy = _prepare_views_copy(tmp_path)
    spec = {
        "entry_id": "entry-1",
        "display_name": "E2E",
        "states": states,
        "data": _LIVE_SNAPSHOT,
    }
    out = json.loads(
        _run_node(
            tmp_path,
            _NODE_VIEWS_LIVE_RUNNER,
            [str(views_copy), json.dumps(spec)],
            "runner_panel_views_live",
        )
    )
    return out["html"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_panel_prefers_live_label_and_emoji_over_stale_snapshot(tmp_path):
    """[REQ-HOM-112] Panel: Live-Attribute schlagen den veralteten Snapshot."""
    html = _render_views_with_live(tmp_path, _live_states(with_attributes=True))

    header = re.search(r'<div class="tile-row">.*?</div>', html, re.S)
    assert header is not None, "die Kopfzeile des Wohlbefinden-Tabs fehlt"
    header_html = header.group(0)
    assert "Zuletzt:" in header_html, f"die Kopfzeile des Wohlbefinden-Tabs fehlt: {header_html}"
    assert _LIVE_LABEL in header_html, f"die Kopfzeile zeigt nicht das Live-Label: {header_html}"
    assert _SNAPSHOT_LABEL not in header_html, (
        f"die Kopfzeile zeigt den veralteten Snapshot-Text: {header_html}"
    )
    assert _LIVE_EMOJI in header_html, f"die Kopfzeile zeigt nicht das Live-Emoji: {header_html}"
    assert _SNAPSHOT_EMOJI not in header_html, (
        f"die Kopfzeile zeigt das veraltete Snapshot-Emoji: {header_html}"
    )

    # Der Chart nutzt dieselbe (live aufgeloeste) Quelle.
    svg = _svg_of(html)
    assert _LIVE_LABEL in _aria_label(svg), (
        f"die aria-label nennt nicht das Live-Label: {_aria_label(svg)!r}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_panel_falls_back_to_snapshot_label_and_emoji(tmp_path):
    """[REQ-HOM-112] Panel ohne Live-Attribute: der Snapshot ist die Quelle."""
    html = _render_views_with_live(tmp_path, _live_states(with_attributes=False))

    header = re.search(r'<div class="tile-row">.*?</div>', html, re.S)
    assert header is not None, "die Kopfzeile des Wohlbefinden-Tabs fehlt"
    header_html = header.group(0)
    assert "Zuletzt:" in header_html, f"die Kopfzeile des Wohlbefinden-Tabs fehlt: {header_html}"
    assert _SNAPSHOT_LABEL in header_html, (
        f"ohne Live-Attribute wird der Snapshot-Text nicht angezeigt: {header_html}"
    )
    assert _LIVE_LABEL not in header_html, (
        f"ohne Live-Attribute darf kein Live-Text erscheinen: {header_html}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_card_prefers_live_label_and_emoji_over_stale_snapshot(tmp_path):
    """[REQ-HOM-112] Card: Live-Attribute schlagen den veralteten Snapshot."""
    case = _card_case([], _CURRENT_A, str(_CURRENT_A["score"]))
    case["states"] = _card_entity_states(str(_CURRENT_A["score"]), _LIVE_LABEL, _LIVE_EMOJI)
    rendered = _card_wellbeing_html(tmp_path, [case])[0]
    html = rendered["html"]

    assert _LIVE_LABEL in html, f"die Karte zeigt nicht das Live-Label: {html!r}"
    assert _SNAPSHOT_LABEL not in html, f"die Karte zeigt den veralteten Snapshot-Text: {html!r}"
    assert _LIVE_EMOJI in html, f"die Karte zeigt nicht das Live-Emoji: {html!r}"
    assert _SNAPSHOT_EMOJI not in html, f"die Karte zeigt das veraltete Snapshot-Emoji: {html!r}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_112_card_falls_back_to_snapshot_label_and_emoji(tmp_path):
    """[REQ-HOM-112] Card ohne Live-Attribute: der Snapshot ist die Quelle."""
    case = _card_case([], _CURRENT_A, str(_CURRENT_A["score"]))
    case["states"] = _card_entity_states(str(_CURRENT_A["score"]), None, None)
    rendered = _card_wellbeing_html(tmp_path, [case])[0]
    html = rendered["html"]

    assert _SNAPSHOT_LABEL in html, (
        f"ohne Live-Attribute wird der Snapshot-Text nicht angezeigt: {html!r}"
    )
    assert _LIVE_LABEL not in html, f"ohne Live-Attribute darf kein Live-Text erscheinen: {html!r}"


# --- Wohlbefinden-Verlauf unter dem Chart (Plan §6 / Decision E6) -----------


def _wellbeing_history_css(text: str) -> str:
    """CSS-Regeln der Verlaufsliste (`.wb-history` / `.wb-hist…`)."""
    return "\n".join(re.findall(r"\.wb-hi(?:story|st)[^{]*\{[^}]*\}", text))


def test_panel_wellbeing_history_lists_time_emoji_label_and_score():
    """[REQ-HOM-112] Die Verlaufsliste unter dem Chart zeigt alle vier Felder.

    Die Liste bleibt reine Anzeige: kein rohes JSON, alle Texte escaped.
    """
    views = _panel_views_source()
    body = _js_function_block(views, "wellbeingTab")

    # Letzte 20 Eintraege aus `wellbeing.history`, als Liste unter dem Chart.
    assert "slice(-20)" in body
    # Neueste Meldung oben; der Chart bleibt unveraendert chronologisch.
    assert re.search(r"slice\(-20\)\s*\.reverse\(\)", body), (
        "die Verlaufsliste ist nicht neueste-zuerst sortiert"
    )
    assert 'class="wb-history"' in body
    assert 'class="wb-hist-label"' in body
    assert 'class="wb-hist-score"' in body
    # Zeitpunkt (relativ), Emoji, Label und Score pro Eintrag …
    assert "relativeTime(entry.ts)" in body
    assert "wellbeingScore(entry)" in body
    assert "scoreMax" in body and "WELLBEING_SCORE_MAX" in body
    assert "entry.emoji" in body and "entry.label" in body
    # … alle Texte escaped, kein JSON-Dump.
    for value in ("entryLabel", "entryAt"):
        assert f"escapeHtml({value}" in body, f"{value} wird nicht escaped"
    assert "wellbeingVisual(entryVisual)" in body, (
        "Emoji/Bild wird nicht ueber wellbeingVisual gerendert"
    )
    assert "JSON.stringify" not in body, "die Historie wird als rohes JSON gerendert"

    # Reihenfolge: Chart zuerst, Liste darunter.
    assert "${chartHtml}${histHtml}" in views, "die Verlaufsliste steht nicht unter dem Score-Chart"


def test_panel_wellbeing_history_css_is_mobile_readable():
    """Die Verlaufsliste hat eigenes CSS (Zeile, Label, Zeit, Score)."""
    css = _wellbeing_history_css(_panel_base_source())

    assert css, "CSS fuer die Verlaufsliste fehlt im Basis-Modul"
    for selector in (".wb-hist-label", ".wb-hist-time", ".wb-hist-score"):
        assert selector in css, f"{selector} fehlt im CSS der Verlaufsliste"


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_panel_wellbeing_history_renders_escaped_entries(tmp_path):
    """[REQ-HOM-112] Gerenderte Verlaufsliste: Emoji, Label, Zeit und Score.

    Enthaelt zusaetzlich einen HOSTILE Eintrag (`<img …>`/`<b>` in Label und
    Emoji): er muss escaped im Output landen, nicht als Markup.
    """
    views_copy = _prepare_views_copy(tmp_path)
    data = json.loads(json.dumps(_PANEL_STALE_SNAPSHOT))
    data["wellbeing"]["history"].append(
        {
            "ts": "2026-10-19T09:30:00+02:00",
            "key": "great",
            "label": "<img src=x onerror=alert(1)>",
            "emoji": "<b>",
            "score": 5,
        }
    )
    spec = {
        "entry_id": "entry-1",
        "display_name": "Alex",
        "live_wellbeing": "unknown",
        "live_score": 4,
        "data": data,
    }

    out = json.loads(
        _run_node(
            tmp_path,
            _NODE_VIEWS_RUNNER,
            [str(views_copy), json.dumps(spec)],
            "runner_panel_history",
        )
    )
    html = out["html"]

    match = re.search(r'<ul class="wb-history">(.*?)</ul>', html, re.S)
    assert match is not None, "die Verlaufsliste fehlt im gerenderten Tab"
    history_html = match.group(1)

    # Der Historieneintrag traegt Label, Emoji, relativen Zeitpunkt und Score.
    assert "Sehr schlecht" in history_html
    assert "\U0001f635" in history_html
    assert "1 / 10" in history_html
    assert re.search(r"vor \d+ |gerade eben", history_html), (
        f"der Zeitpunkt der Verlaufsliste fehlt: {history_html}"
    )
    # Der aktuelle Live-Wert (4) gehoert NICHT in die Verlaufsliste.
    assert "4 / 10" not in history_html
    # Kein rohes JSON.
    assert '{"' not in history_html

    # Hostile Felder sind escaped — kein Markup aus Nutzerdaten.
    assert "&lt;img src=x onerror=alert(1)&gt;" in history_html, (
        f"das hostile Label ist nicht escaped: {history_html}"
    )
    assert "&lt;b&gt;" in history_html, f"das hostile Emoji ist nicht escaped: {history_html}"
    assert "<img src=x" not in history_html
    assert "<b>" not in history_html
    # Neueste Meldung oben: der 09:30-Eintrag steht vor dem 08:00-Eintrag.
    assert history_html.index("&lt;img src=x") < history_html.index("Sehr schlecht"), (
        "die Verlaufsliste ist nicht neueste-zuerst sortiert"
    )

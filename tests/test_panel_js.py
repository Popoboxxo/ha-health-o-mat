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


# Branding-Version je JS-Modul (`console.info`-Ausgabe). Sie beeinflusst den
# Cache-Buster NICHT — der entsteht aus `frontend.integration_version()` —,
# Driftet aber genauso still auseinander wie die `?v=`-Query oben. Deshalb
# dasselbe Guard-Muster: jede Konstante == manifest.version.
_JS_VERSION_CONSTANTS: dict[str, str] = {
    "health-o-mat-panel.js": "PANEL_VERSION",
    "health-o-mat-card.js": "CARD_VERSION",
    "health-o-mat-labs-card.js": "CARD_VERSION",
}

# `const <NAME>_VERSION = "<version>";` am Zeilenanfang (auch in einer Datei mit
# mehreren Modulen/mehreren Konstanten).
_JS_VERSION_CONST_RE = re.compile(
    r"^const\s+([A-Z][A-Z0-9_]*_VERSION)\s*=\s*[\"']([^\"']*)[\"']", re.MULTILINE
)


def test_js_version_constants_match_manifest_version():
    """`PANEL_VERSION`/`CARD_VERSION` aller ausgelieferten JS-Module == manifest.version.

    Prüft zusätzlich, dass die Liste der Versionskonstanten vollständig ist:
    ein neues Modul mit eigener `*_VERSION`-Konstante muss hier eingetragen
    werden, sonst schlägt der Test fehl (kein stiller Drift bei neuen Modulen).
    """
    version = frontend.integration_version()
    assert version and version != "0", "manifest.json lieferte keine brauchbare Version"

    declared: list[tuple[str, str, str]] = []
    for path in sorted(_WWW_DIR.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        for match in _JS_VERSION_CONST_RE.finditer(text):
            declared.append((path.name, match.group(1), match.group(2)))

    found = {(filename, constant_name) for filename, constant_name, _ in declared}
    expected = set(_JS_VERSION_CONSTANTS.items())
    assert found == expected, (
        "JS-Versionskonstanten weichen von der Erwartung ab: "
        f"fehlend={sorted(expected - found)}, unerwartet={sorted(found - expected)}"
    )

    mismatches = [(name, const, value) for name, const, value in declared if value != version]
    assert not mismatches, f"JS-Versionskonstante != manifest.version {version!r}: {mismatches}"


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


def _js_method_block(text: str, name: str) -> str:
    """Quelltext des Methodenrumpfs von `name()` (bis zur Zeile `  }`)."""
    match = re.search(rf"\n\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", text)
    assert match is not None, f"{name}() fehlt im Quelltext"
    end = text.find("\n  }", match.end())
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
    assert re.search(r"aktuell (?:\$\{[^}]*score[^}]*\}|\{score\})", text), (
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
  _wbPending: spec.pending || null,
  _history: spec.history || {},
  _historyFilter: spec.historyFilter || {},
  _historyConfirm: spec.historyConfirm || null,
  _historyStatus: spec.historyStatus || null,
  _historyBusy: false,
  _canUndo: (entryId, kind) => {
    const flags = spec.canUndo || {};
    return Object.prototype.hasOwnProperty.call(flags, kind) ? flags[kind] : true;
  },
  _isWarning: () => false,
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
    (tmp_path / "health-o-mat-i18n.js").write_bytes(
        (_WWW_DIR / "health-o-mat-i18n.js").read_bytes()
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


def test_panel_wellbeing_history_uses_the_history_api_only():
    """[REQ-HOM-115] WB-Verlauf kommt aus `historySection` — keine Dopplung.

    Die bisherige Liste aus `wellbeing.history` ist ersetzt: der Tab rendert
    die API-Liste (eine Quelle), `wellbeing.history` speist nur den Chart.
    """
    views = _panel_views_source()
    body = _js_function_block(views, "wellbeingTab")

    assert 'historySection(panel, entryId, "wellbeing")' in body, (
        "der Wohlbefinden-Tab rendert die History-API-Liste nicht"
    )
    assert 'class="wb-history"' not in views, (
        "die alte WB-Verlaufsliste wird weiterhin gerendert (Dopplung)"
    )
    assert "histHtml" not in body, "die alte Verlaufsliste ist nicht entfernt"

    history = _js_function_block(views, "historySection")
    assert "slice(0, HISTORY_LIMIT)" in history, "die Liste ist nicht auf 50 gedeckelt"
    assert 'data-action="history-filter"' in history
    assert "aria-pressed" in history
    assert 'class="history-list"' in history
    assert 'class="history-item' in views, "die Verlaufszeile fehlt"
    assert 'data-action="history-void"' in views
    assert 'data-action="history-restore"' in views
    assert "Wirklich löschen?" in views
    assert "gelöscht" in views
    # Kein rohes JSON in der Liste.
    assert "JSON.stringify" not in history


def test_panel_history_css_is_mobile_readable():
    """[REQ-HOM-115] Verlauf: Liste, Zeit/Text/Status und <400 px ohne Überlauf."""
    css = _panel_base_source()

    for selector in (
        ".history-list",
        ".history-item",
        ".history-time",
        ".history-text",
        ".history-actions",
        ".history-confirm",
        "@media (max-width: 400px)",
    ):
        assert selector in css, f"{selector} fehlt im CSS des Verlaufs"
    assert "text-decoration: line-through" in css, "gelöschte Einträge sind nicht markiert"
    assert "overflow-wrap: anywhere" in css, "lange Texte können überlaufen"


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_panel_history_renders_kinds_filter_and_inline_confirm(tmp_path):
    """[REQ-HOM-115] Gerenderte API-Liste: drei Typen, Filter, Confirm, Escaping.

    Feeds come exclusively from `_history` (the list_history shape), including
    a hostile label and a voided entry.
    """
    views_copy = _prepare_views_copy(tmp_path)
    entry = "entry-1"
    history = {
        entry: {
            "drinks": {
                "entries": [
                    {
                        "id": "d1",
                        "ts": "2026-10-19T09:30:00+02:00",
                        "ml": 250,
                        "type": "Kaffee",
                        "src": "panel",
                        "voided_at": None,
                    },
                ],
                "includeVoided": False,
            },
            "blood_pressure": {
                "entries": [
                    {
                        "id": "b1",
                        "ts": "2026-10-19T08:00:00+02:00",
                        "sys": 120,
                        "dia": 80,
                        "pulse": 62,
                        "note": "morgens",
                        "voided_at": None,
                    },
                ],
                "includeVoided": False,
            },
            "wellbeing": {
                "entries": [
                    {
                        "id": "w1",
                        "ts": "2026-10-19T09:30:00+02:00",
                        "key": "great",
                        "label": "<img src=x onerror=alert(1)>",
                        "voided_at": None,
                    },
                    {
                        "id": "w0",
                        "ts": "2026-10-19T08:00:00+02:00",
                        "key": "bad",
                        "voided_at": "2026-10-19T10:00:00+02:00",
                    },
                ],
                "includeVoided": True,
            },
        }
    }
    data = json.loads(json.dumps(_PANEL_STALE_SNAPSHOT))
    data["wellbeing"]["history"] = []  # Chart darf die Liste NICHT speisen.

    def render(tab, confirm=None):
        spec = {
            "entry_id": entry,
            "display_name": "Alex",
            "live_wellbeing": "unknown",
            "live_score": 4,
            "data": data,
            "history": history,
            "historyConfirm": confirm,
            "canUndo": {"blood_pressure": True, "wellbeing": True},
        }
        # Der Runner waehlt den Tab ueber `panel._tab`; hier direkt setzen.
        runner = _NODE_VIEWS_RUNNER.replace('_tab: "wellbeing"', f'_tab: "{tab}"')
        path = tmp_path / f"runner_{tab}.mjs"
        path.write_text(runner, encoding="utf-8")
        return json.loads(
            _run_node(tmp_path, path.read_text(), [str(views_copy), json.dumps(spec)], f"r_{tab}")
        )["html"]

    drinks = render("drink")
    assert 'data-history="drinks"' in drinks
    assert "250 ml" in drinks and "Kaffee" in drinks and "Panel" in drinks
    assert 'data-action="history-void"' in drinks
    assert 'aria-pressed="true"' in drinks

    bp = render("bp")
    assert "120/80" in bp and "62 bpm" in bp and "morgens" in bp
    assert 'data-action="undo" data-kind="blood_pressure"' in bp

    wb = render("wellbeing")
    assert 'data-history="wellbeing"' in wb
    assert "9 / 10" in wb
    assert "gelöscht" in wb, "gelöschter Eintrag ist nicht markiert"
    assert 'data-action="history-restore"' in wb
    assert "&lt;img src=x onerror=alert(1)&gt;" in wb, "hostiles Label ist nicht escaped"
    assert "<img src=x" not in wb
    assert 'class="wb-history"' not in wb, "die alte WB-Liste ist wieder da"

    confirm = render("drink", {"entryId": entry, "kind": "drinks", "id": "d1"})
    assert "Wirklich löschen?" in confirm
    assert 'data-action="history-void-confirm"' in confirm
    assert 'data-action="history-void-cancel"' in confirm


def test_panel_undo_is_disabled_without_drinks():
    """[Undo] Panel deaktiviert den Undo-Button ohne Getränkebuchung."""
    views = _panel_views_source()
    drink_tab = _js_function_block(views, "drinkTab")
    entry = (_WWW_DIR / "health-o-mat-panel.js").read_text(encoding="utf-8")

    assert "data.undo" in drink_tab and "canUndo" in drink_tab
    assert "Keine Getränkebuchung" in drink_tab
    assert "data.undo.drink === false" in entry


def test_panel_admin_settings_include_wellbeing_images():
    """[Admin] Die Personen-Einstellungen bieten Bildfelder je Wellbeing-Key."""
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")
    entry = (_WWW_DIR / "health-o-mat-panel.js").read_text(encoding="utf-8")

    assert "Wohlbefinden-Bilder" in admin
    assert "wb-image-" in admin
    assert "WELLBEING_STATES.map" in admin
    assert "wellbeing_images: wellbeingImages" in entry


# --- REQ-HOM-114: Wohlbefinden-Bestätigung vor Übernahme --------------------

_PENDING_HINT = "noch nicht übernommen"


def test_req_hom_114_panel_admin_has_wellbeing_confirm_checkbox():
    """[REQ-HOM-114] Admin-Maske: Checkbox im Wohlbefinden-Bereich."""
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")
    base = _panel_base_source()
    entry = (_WWW_DIR / "health-o-mat-panel.js").read_text(encoding="utf-8")

    assert 'data-field="wellbeing_confirm"' in admin
    assert "Wohlbefinden: Bestätigung vor Übernahme" in admin
    # Fallback der Anzeige (Default aus) im Basis-Modul.
    assert re.search(r"wellbeing_confirm:\s*false", base)
    # Sammeln + PATCH-Vergleich im Entry-Modul (gleicher set_settings-Pfad).
    assert "wellbeing_confirm: wellbeingConfirm" in entry
    assert "out.wellbeing_confirm = payload.wellbeing_confirm" in entry


def test_req_hom_114_panel_views_show_pending_selection_and_confirm_button(tmp_path):
    """[REQ-HOM-114] Vorgemerkte Auswahl ist markiert und nur bestätigbar."""
    views_copy = _prepare_views_copy(tmp_path)
    data = json.loads(json.dumps(_PANEL_STALE_SNAPSHOT))
    data["wellbeing_confirm"] = True
    spec = {
        "entry_id": "entry-1",
        "display_name": "Alex",
        "live_wellbeing": "unknown",
        "live_score": 2,
        "data": data,
        "pending": {"entryId": "entry-1", "key": "great", "score": None},
    }

    html = json.loads(
        _run_node(
            tmp_path,
            _NODE_VIEWS_RUNNER,
            [str(views_copy), json.dumps(spec)],
            "runner_panel_confirm",
        )
    )["html"]

    assert re.search(r'class="wb-btn[^"]*pending[^"]*"[^>]*data-key="great"', html), (
        "die vorgemerkte Stufe ist nicht als `pending` markiert"
    )
    # Gespeicherter Zustand bleibt `active`, die Vormerkung ist eine eigene Klasse.
    assert re.search(r'class="wb-btn active[^"]*"[^>]*data-key="bad"', html), (
        "der gespeicherte Zustand ist nicht mehr als `active` markiert"
    )
    assert 'data-action="wb-confirm"' in html, "der Bestätigungsbutton fehlt"
    assert "Übernehmen" in html
    assert _PENDING_HINT in html


def test_req_hom_114_panel_views_confirm_button_only_with_pending(tmp_path):
    """[REQ-HOM-114] Ohne Vormerkung (bzw. ohne Option) kein Bestätigungsbutton."""
    views_copy = _prepare_views_copy(tmp_path)
    data = json.loads(json.dumps(_PANEL_STALE_SNAPSHOT))
    data["wellbeing_confirm"] = True
    base_spec = {
        "entry_id": "entry-1",
        "display_name": "Alex",
        "live_wellbeing": "unknown",
        "live_score": 2,
        "data": data,
    }

    without_pending = json.loads(
        _run_node(
            tmp_path,
            _NODE_VIEWS_RUNNER,
            [str(views_copy), json.dumps(base_spec)],
            "runner_panel_no_pending",
        )
    )["html"]
    assert 'data-action="wb-confirm"' not in without_pending
    assert "pending" not in re.findall(r'class="wb-btn([^"]*)"', without_pending)[0]

    data_disabled = json.loads(json.dumps(_PANEL_STALE_SNAPSHOT))
    data_disabled["wellbeing_confirm"] = False
    spec = dict(base_spec, data=data_disabled, pending={"entryId": "entry-1", "key": "great"})

    disabled = json.loads(
        _run_node(
            tmp_path,
            _NODE_VIEWS_RUNNER,
            [str(views_copy), json.dumps(spec)],
            "runner_panel_confirm_disabled",
        )
    )["html"]
    assert 'data-action="wb-confirm"' not in disabled, (
        "der Bestätigungsbutton erscheint trotz deaktivierter Option"
    )
    assert not re.search(r'class="wb-btn[^"]*pending[^"]*"[^>]*data-key="great"', disabled)


# Node-Runner: laedt die echten Panel-ES-Module (Kopien ohne Cache-Buster) und
# prueft das KLICKVERHALTEN des Entry-Moduls (kein sofortiger Service-Aufruf).
_NODE_PANEL_CONFIRM_RUNNER = """import { pathToFileURL } from "node:url";

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; }
  addEventListener() {}
  removeEventListener() {}
  querySelector() { return null; }
}

class FakeHTMLElement {
  constructor() { this._shadow = null; }
  attachShadow() {
    this._shadow = new FakeShadowRoot();
    return this._shadow;
  }
  get shadowRoot() { return this._shadow; }
}

let PanelClass = null;
globalThis.HTMLElement = FakeHTMLElement;
globalThis.customElements = {
  get: () => undefined,
  define: (_name, cls) => { PanelClass = cls; },
};
// Das Modul loggt beim Laden auf stdout — der Runner schreibt JSON dorthin.
console.info = () => {};

await import(pathToFileURL(process.argv[2]).href);

function makePanel(confirm) {
  const panel = new PanelClass();
  panel._selectedEntry = "entry-1";
  panel._view = "detail";
  panel._data = { "entry-1": { wellbeing_confirm: confirm } };
  panel._busy = false;
  panel._render = () => {};
  panel._calls = [];
  panel._setWellbeing = (...args) => { panel._calls.push(args); };
  return panel;
}

function clickWb(panel, key) {
  panel._onClick({
    target: {
      closest: () => ({
        getAttribute: (name) => (name === "data-action" ? "wb" : key),
      }),
    },
  });
}

const staged = makePanel(true);
clickWb(staged, "great");

const immediate = makePanel(false);
clickWb(immediate, "great");

const confirmed = makePanel(true);
clickWb(confirmed, "good");
await confirmed._confirmWellbeing();

const switched = makePanel(true);
clickWb(switched, "good");
switched._openPerson("entry-2", { silent: true });

const overview = makePanel(true);
clickWb(overview, "good");
overview._showOverview({ silent: true });

const reloaded = makePanel(true);
clickWb(reloaded, "good");
await reloaded._reloadEntry("entry-1");

process.stdout.write(
  JSON.stringify({
    staged: { pending: staged._wbPending, calls: staged._calls },
    immediate: { pending: immediate._wbPending, calls: immediate._calls },
    confirmed: { pending: confirmed._wbPending, calls: confirmed._calls },
    switched: { pending: switched._wbPending },
    overview: { pending: overview._wbPending },
    reloaded: { pending: reloaded._wbPending },
  })
);
"""


def _prepare_panel_copy(tmp_path) -> Path:
    """Kopien ALLER Panel-Module ohne `?v=`-Query (Node-ESM-tauglich)."""
    for name in (
        "health-o-mat-panel-base.js",
        "health-o-mat-panel-views.js",
        "health-o-mat-panel-admin.js",
        "health-o-mat-panel.js",
        "health-o-mat-i18n.js",
    ):
        source = (_WWW_DIR / name).read_text(encoding="utf-8")
        patched = re.sub(r'"(\./health-o-mat-panel[^"]*?\.js)\?v=[^"]+"', r'"\1"', source)
        (tmp_path / name).write_text(patched, encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"type": "module"}), encoding="utf-8")
    return tmp_path / "health-o-mat-panel.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_114_panel_defers_wellbeing_report_until_confirmation(tmp_path):
    """[REQ-HOM-114] Panel: Klick merkt vor, erst „Übernehmen" meldet.

    Kontrollfall `wellbeing_confirm=false`: der Klick meldet sofort (bisheriges
    Verhalten). Zusätzlich: Personenwechsel und Übersicht verwerfen die
    Vormerkung, ein Reload ebenfalls.
    """
    panel_copy = _prepare_panel_copy(tmp_path)
    out = json.loads(
        _run_node(
            tmp_path,
            _NODE_PANEL_CONFIRM_RUNNER,
            [str(panel_copy)],
            "runner_panel_confirm_behaviour",
        )
    )

    assert out["staged"]["calls"] == [], (
        "der Klick loest trotz Bestätigungsmodus sofort `_setWellbeing` aus"
    )
    assert out["staged"]["pending"] == {
        "entryId": "entry-1",
        "key": "great",
        "score": None,
        "ts": "",
    }

    assert len(out["immediate"]["calls"]) == 1, (
        "ohne Bestätigungsmodus wird die Meldung nicht sofort gesendet"
    )
    assert out["immediate"]["calls"][0] == ["entry-1", "great", None, ""]
    assert out["immediate"]["pending"] is None

    assert out["confirmed"]["calls"] == [["entry-1", "good", None, ""]], (
        "der Bestätigungsbutton sendet die vorgemerkte Auswahl nicht"
    )

    assert out["switched"]["pending"] is None, "die Vormerkung überlebt den Personenwechsel"
    assert out["overview"]["pending"] is None, "die Vormerkung überlebt den Wechsel zur Übersicht"
    # S1: `_reloadEntry` ist KEIN Reset-Pfad mehr — ein unbeteiligter Reload
    # (Getränk/Undo/BD) darf die Vormerkung nicht verwerfen.
    assert out["reloaded"]["pending"] == {
        "entryId": "entry-1",
        "key": "good",
        "score": None,
        "ts": "",
    }, "ein unbeteiligter Reload verwirft die Vormerkung"


# --- REQ-HOM-114: Pending-Lifecycle + Admin-Wiring (Verhalten, kein String) ---

_NODE_PANEL_PENDING_RUNNER = """import { pathToFileURL } from "node:url";

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; this._fields = {}; }
  addEventListener() {}
  removeEventListener() {}
  querySelector(selector) {
    const match = /\\[data-field="([^"]+)"\\]/.exec(String(selector));
    const field = match ? match[1] : "";
    return this._fields[field] || null;
  }
  querySelectorAll() { return []; }
}

class FakeHTMLElement {
  constructor() { this._shadow = null; }
  attachShadow() { this._shadow = new FakeShadowRoot(); return this._shadow; }
  get shadowRoot() { return this._shadow; }
}

let PanelClass = null;
globalThis.HTMLElement = FakeHTMLElement;
globalThis.customElements = {
  get: () => undefined,
  define: (_name, cls) => { PanelClass = cls; },
};
console.info = () => {};

await import(pathToFileURL(process.argv[2]).href);

const SET_WELLBEING = "health_o_mat/set_wellbeing";
const PANEL_DATA = "health_o_mat/panel_data";

function makePanel() {
  const panel = new PanelClass();
  panel._selectedEntry = "entry-1";
  panel._view = "detail";
  panel._tab = "wellbeing";
  panel._data = {
    "entry-1": {
      wellbeing_confirm: true,
      wellbeing_scale: Array.from({ length: 10 }, (_, i) => ({
        key: `k${i + 1}`,
        label: `Stufe ${i + 1}`,
      })),
    },
    "entry-2": { wellbeing_confirm: true },
  };
  panel._persons = [
    { entry_id: "entry-1", display_name: "Alex" },
    { entry_id: "entry-2", display_name: "Bea" },
  ];
  panel._settings = {};
  panel._quickDraft = [];
  panel._busy = false;
  panel._render = () => {};
  panel._messages = [];
  panel._failSetWellbeing = false;
  panel._ws = async (msg) => {
    panel._messages.push(msg);
    if (panel._failSetWellbeing && msg.type === SET_WELLBEING) {
      throw new Error("Server nicht erreichbar");
    }
    if (msg.type === PANEL_DATA) return { entities: {} };
    if (msg.type === "health_o_mat/list_persons") return { persons: panel._persons };
    if (msg.type === "health_o_mat/get_settings") return { wellbeing_confirm: true };
    return {};
  };
  panel._hass = { user: { is_admin: true }, states: {}, connection: {} };
  return panel;
}

function sentWellbeing(panel) {
  return panel._messages.filter((msg) => msg.type === SET_WELLBEING);
}

/* S1: unbeteiligte Schreibvorgaenge duerfen die Vormerkung nicht verwerfen. */
const drink = makePanel();
drink._stageWellbeing("entry-1", "k3", null);
await drink._book("entry-1", 250);

const reload = makePanel();
reload._stageWellbeing("entry-1", "k3", null);
await reload._reloadEntry("entry-1");

/* S4a: Zahleneingabe im Bestaetigungsmodus merkt nur vor. */
const score = makePanel();
score.shadowRoot._fields["wb-score"] = { value: "7" };
score._submitWellbeing();
const scoreStaged = { pending: score._wbPending, sent: sentWellbeing(score).length };
await score._confirmWellbeing();
const scoreConfirmed = { pending: score._wbPending, sent: sentWellbeing(score) };

/* S4b: fehlgeschlagene Uebernahme behaelt die Vormerkung. */
const failed = makePanel();
failed._stageWellbeing("entry-1", "k3", null);
failed._failSetWellbeing = true;
await failed._confirmWellbeing();

/* S4c: erfolgreiche Uebernahme loescht die Vormerkung. */
const confirmed = makePanel();
confirmed._stageWellbeing("entry-1", "k3", null);
await confirmed._confirmWellbeing();

/* G1: Eintritt in die Admin-Einstellungen verwirft die Detail-Vormerkung. */
const settings = makePanel();
settings._stageWellbeing("entry-1", "k3", null);
settings._openSettings();

/* S5: Admin-Formular wirklich auslesen und gegen den Serverstand diffen. */
const admin = makePanel();
admin._settings = {
  "entry-1": {
    daily_goal_ml: 2000,
    daily_reset_hour: 2,
    person_display: "Alex",
    quick_drinks: [{ key: "slot_0", label: "Wasser", ml: 250, icon: "mdi-cup" }],
    drink_lexicon: "wasser=Wasser,250",
    wellbeing_images: {},
    sys_threshold: 140,
    dia_threshold: 90,
    retention_months: 12,
    audit_limit: 1000,
    enable_sidebar_panel: false,
    wellbeing_confirm: false,
    areas: { drink: true, bp: true, wellbeing: true },
  },
};
admin._quickDraft = [{ key: "slot_0", label: "Wasser", ml: 250, icon: "mdi-cup" }];
admin.shadowRoot._fields = {
  daily_goal_ml: { value: "2000" },
  daily_reset_hour: { value: "2" },
  person_display: { value: "Alex" },
  sys_threshold: { value: "140" },
  dia_threshold: { value: "90" },
  retention_months: { value: "12" },
  audit_limit: { value: "1000" },
  drink_lexicon: { value: "wasser=Wasser,250" },
  enable_sidebar_panel: { checked: false },
  wellbeing_confirm: { checked: true },
  "area-drink": { checked: true },
  "area-bp": { checked: true },
  "area-wellbeing": { checked: true },
};
const collected = admin._collectSettingsPayload();
const changes = admin._changedSettings("entry-1", collected.payload);

process.stdout.write(
  JSON.stringify({
    drink: { pending: drink._wbPending, types: drink._messages.map((msg) => msg.type) },
    reload: { pending: reload._wbPending },
    scoreStaged,
    scoreConfirmed,
    failed: { pending: failed._wbPending, error: failed._actionError },
    confirmed: { pending: confirmed._wbPending, sent: sentWellbeing(confirmed) },
    settings: { pending: settings._wbPending },
    admin: { errors: collected.errors, payload: collected.payload, changes },
  })
);
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_114_panel_pending_survives_unrelated_writes(tmp_path):
    """[REQ-HOM-114] S1/S4/G1: Pending nur in Reset-Pfaden bzw. nach Erfolg weg."""
    panel_copy = _prepare_panel_copy(tmp_path)
    out = json.loads(
        _run_node(
            tmp_path,
            _NODE_PANEL_PENDING_RUNNER,
            [str(panel_copy)],
            "runner_panel_pending_lifecycle",
        )
    )

    # S1: Getraenkebuchung und ein unbeteiligter Reload lassen sie stehen.
    assert out["drink"]["pending"] == {
        "entryId": "entry-1",
        "key": "k3",
        "score": None,
        "ts": "",
    }, "eine Getraenkebuchung verwirft die vorgemerkte Auswahl"
    assert out["reload"]["pending"] == {
        "entryId": "entry-1",
        "key": "k3",
        "score": None,
        "ts": "",
    }, "`_reloadEntry` verwirft die vorgemerkte Auswahl"

    # S4a: Zahleneingabe merkt vor, sendet nichts, Bestaetigung sendet den Score.
    staged = out["scoreStaged"]
    assert staged["pending"] == {"entryId": "entry-1", "key": "", "score": 7, "ts": ""}, (
        "die Zahleneingabe wird nicht (mit Personenbezug) vorgemerkt"
    )
    assert staged["sent"] == 0, "die Zahleneingabe meldet trotz Bestaetigungsmodus sofort"
    confirmed_score = out["scoreConfirmed"]
    assert len(confirmed_score["sent"]) == 1, "die Bestaetigung sendet den Score nicht"
    assert confirmed_score["sent"][0]["score"] == 7
    assert "key" not in confirmed_score["sent"][0]
    assert confirmed_score["pending"] is None

    # S4b: Fehler laesst die Vormerkung stehen.
    failed = out["failed"]
    assert failed["pending"] is not None, (
        "die Vormerkung geht bei einer fehlgeschlagenen Uebernahme verloren"
    )
    assert failed["error"], "der Fehler wird nicht gemeldet"

    # S4c: Erfolg loescht die Vormerkung.
    confirmed = out["confirmed"]
    assert len(confirmed["sent"]) == 1
    assert confirmed["sent"][0]["key"] == "k3"
    assert confirmed["pending"] is None, "die Vormerkung ueberlebt die erfolgreiche Uebernahme"

    # G1: Admin-Einstellungen sind ein Reset-Pfad.
    assert out["settings"]["pending"] is None, (
        "eine Detail-Vormerkung ueberlebt den Eintritt in die Admin-Einstellungen"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_114_panel_admin_payload_carries_wellbeing_confirm(tmp_path):
    """[REQ-HOM-114] S5: `_collectSettingsPayload`/`_changedSettings` verdrahtet."""
    panel_copy = _prepare_panel_copy(tmp_path)
    out = json.loads(
        _run_node(
            tmp_path,
            _NODE_PANEL_PENDING_RUNNER,
            [str(panel_copy)],
            "runner_panel_settings_payload",
        )
    )["admin"]

    assert out["errors"] == [], f"das Formular meldet Fehler: {out['errors']}"
    assert out["payload"]["wellbeing_confirm"] is True, "die Admin-Checkbox landet nicht im Payload"
    assert out["changes"] == {"wellbeing_confirm": True}, (
        f"das Change-Set traegt den Schalter nicht korrekt: {out['changes']!r}"
    )


# --- M2b: Audit-Log-Limit im Admin-Formular ---------------------------------

_NODE_AUDIT_LIMIT_RUNNER = """import { pathToFileURL } from "node:url";

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; this._fields = {}; }
  addEventListener() {}
  removeEventListener() {}
  querySelector(selector) {
    const match = /\\[data-field="([^"]+)"\\]/.exec(String(selector));
    const field = match ? match[1] : "";
    return this._fields[field] || null;
  }
  querySelectorAll() { return []; }
}

class FakeHTMLElement {
  constructor() { this._shadow = null; }
  attachShadow() { this._shadow = new FakeShadowRoot(); return this._shadow; }
  get shadowRoot() { return this._shadow; }
}

let PanelClass = null;
globalThis.HTMLElement = FakeHTMLElement;
globalThis.customElements = {
  get: () => undefined,
  define: (_name, cls) => { PanelClass = cls; },
};
console.info = () => {};

await import(pathToFileURL(process.argv[2]).href);

function makePanel() {
  const panel = new PanelClass();
  panel._selectedEntry = "entry-1";
  panel._view = "settings";
  panel._persons = [{ entry_id: "entry-1", display_name: "Alex" }];
  panel._quickDraft = [{ key: "slot_0", label: "Wasser", ml: 250, icon: "mdi-cup" }];
  panel._settings = {
    "entry-1": {
      daily_goal_ml: 2000,
      daily_reset_hour: 0,
      person_display: "Alex",
      quick_drinks: [{ key: "slot_0", label: "Wasser", ml: 250, icon: "mdi-cup" }],
      drink_lexicon: "wasser=Wasser,250",
      wellbeing_images: {},
      sys_threshold: 140,
      dia_threshold: 90,
      retention_months: 0,
      audit_limit: 1000,
      enable_sidebar_panel: false,
      wellbeing_confirm: false,
      areas: { drink: true, bp: true, wellbeing: true },
    },
  };
  panel._render = () => {};
  panel._messages = [];
  panel._ws = async () => ({});
  panel._hass = { user: { is_admin: true }, states: {}, connection: {} };
  return panel;
}

function fields(audit) {
  return {
    daily_goal_ml: { value: "2000" },
    daily_reset_hour: { value: "0" },
    person_display: { value: "Alex" },
    sys_threshold: { value: "140" },
    dia_threshold: { value: "90" },
    retention_months: { value: "0" },
    audit_limit: { value: audit },
    drink_lexicon: { value: "wasser=Wasser,250" },
    enable_sidebar_panel: { checked: false },
    wellbeing_confirm: { checked: false },
    "area-drink": { checked: true },
    "area-bp": { checked: true },
    "area-wellbeing": { checked: true },
  };
}

function run(audit) {
  const panel = makePanel();
  panel.shadowRoot._fields = fields(audit);
  const collected = panel._collectSettingsPayload();
  return {
    payload: collected.payload.audit_limit,
    errors: collected.errors,
    changes: panel._changedSettings("entry-1", collected.payload),
  };
}

process.stdout.write(
  JSON.stringify({
    unchanged: run("1000"),
    zero: run("0"),
    negative: run("-1"),
    text: run("abc"),
  })
);
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_m2b_panel_audit_limit_payload_and_change_set(tmp_path):
    """[M2b] `audit_limit` wird gelesen, validiert und nur bei Änderung gesendet."""
    panel_copy = _prepare_panel_copy(tmp_path)
    out = json.loads(
        _run_node(
            tmp_path,
            _NODE_AUDIT_LIMIT_RUNNER,
            [str(panel_copy)],
            "runner_panel_audit_limit",
        )
    )

    unchanged = out["unchanged"]
    assert unchanged["errors"] == [], f"Formular meldet Fehler: {unchanged['errors']}"
    assert unchanged["payload"] == 1000
    assert unchanged["changes"] == {}, "unveraendertes Limit wird faelschlich gesendet"

    zero = out["zero"]
    assert zero["errors"] == [], "0 (unbegrenzt) wird als ungueltig abgelehnt"
    assert zero["payload"] == 0
    assert zero["changes"] == {"audit_limit": 0}, f"Change-Set: {zero['changes']!r}"

    for key in ("negative", "text"):
        invalid = out[key]
        assert invalid["errors"], f"{key} wird nicht abgelehnt"
        assert any("Audit" in message for message in invalid["errors"]), invalid["errors"]


def test_m2b_panel_audit_limit_field_is_wired_into_admin_form():
    """[M2b] Das Admin-Feld sitzt in der Karte „Datenhaltung" (number, min 0)."""
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")
    assert "Audit-Log-Limit (0 = unbegrenzt)" in admin
    assert 'data-field="audit_limit"' in admin
    assert "SETTINGS_FALLBACKS.audit_limit" in admin

    base = _panel_base_source()
    assert "audit_limit: 1000" in base
    assert "auditMin: 0" in base


# --- REQ-HOM-120: Rückdatierung im Panel ------------------------------------

_NODE_PANEL_TS_RUNNER = """import { pathToFileURL } from "node:url";

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; this._fields = {}; }
  addEventListener() {}
  removeEventListener() {}
  querySelector(selector) {
    const match = /\\[data-field="([^"]+)"\\]/.exec(String(selector));
    const field = match ? match[1] : "";
    return this._fields[field] || null;
  }
  querySelectorAll() { return []; }
}

class FakeHTMLElement {
  constructor() { this._shadow = null; }
  attachShadow() { this._shadow = new FakeShadowRoot(); return this._shadow; }
  get shadowRoot() { return this._shadow; }
}

let PanelClass = null;
globalThis.HTMLElement = FakeHTMLElement;
globalThis.customElements = { get: () => undefined, define: (_n, cls) => { PanelClass = cls; } };
console.info = () => {};

await import(pathToFileURL(process.argv[2]).href);

function makePanel(confirm) {
  const panel = new PanelClass();
  panel._selectedEntry = "entry-1";
  panel._view = "detail";
  panel._data = { "entry-1": { wellbeing_confirm: confirm } };
  panel._busy = false;
  panel._render = () => {};
  panel._messages = [];
  panel._ws = async (msg) => { panel._messages.push(msg); return {}; };
  panel._reloadEntry = async () => {};
  panel.shadowRoot._fields = {
    "drink-ts": { value: "" },
    "bp-ts": { value: "" },
    "wb-ts": { value: "" },
  };
  return panel;
}

function messagesOf(panel) {
  return panel._messages.map((msg) => ({
    type: msg.type,
    ts: msg.ts || "",
    ml: msg.ml,
  }));
}

/* Getränk: bewusster Zeitpunkt wird gesendet, danach Feld zurückgesetzt. */
const drink = makePanel(false);
drink.shadowRoot._fields["drink-ts"].value = "2026-10-24T18:30";
await drink._book("entry-1", 250, "Wasser");
const drinkAfter = {
  messages: messagesOf(drink),
  draft: drink._tsDraft["drink-ts"],
  field: drink.shadowRoot._fields["drink-ts"].value,
};

/* Getränk: Zukunft wird clientseitig abgelehnt (keine stille Buchung). */
const future = makePanel(false);
future.shadowRoot._fields["drink-ts"].value = "2999-01-01T10:00";
await future._book("entry-1", 250, "Wasser");
const futureResult = { messages: messagesOf(future), error: future._actionError };

/* Schnellwahl „Gestern" setzt Entwurf + Feld ohne Render. */
const quick = makePanel(false);
quick._onClick({
  target: {
    closest: () => ({
      getAttribute: (name) => (name === "data-action" ? "drink-ts-yesterday" : ""),
    }),
  },
});
const yesterday = new Date();
yesterday.setDate(yesterday.getDate() - 1);
const pad = (n) => String(n).padStart(2, "0");
const expectedYesterday = `${yesterday.getFullYear()}-${pad(yesterday.getMonth() + 1)}-${pad(
  yesterday.getDate()
)}T${pad(yesterday.getHours())}:${pad(yesterday.getMinutes())}`;
const quickResult = {
  draft: quick._tsDraft["drink-ts"],
  field: quick.shadowRoot._fields["drink-ts"].value,
  expected: expectedYesterday,
};

/* Blutdruck: ts wird mitgesendet. */
const bp = makePanel(false);
bp.shadowRoot._fields["bp-ts"].value = "2026-10-24T07:15";
await bp._saveMeasurement("entry-1", 120, 80, null, "");
const bpResult = { messages: messagesOf(bp), draft: bp._tsDraft["bp-ts"] };

/* Wohlbefinden: Vormerkung trägt den Zeitpunkt, erst „Übernehmen" sendet ihn. */
const wb = makePanel(true);
wb.shadowRoot._fields["wb-ts"].value = "2026-10-23T20:00";
wb._stageWellbeing("entry-1", "great", null);
const wbStaged = { pending: wb._wbPending, sent: messagesOf(wb) };
await wb._confirmWellbeing();
const wbConfirmed = { pending: wb._wbPending, sent: messagesOf(wb) };

/* Wohlbefinden: Zukunft wird im Formularpfad verständlich gemeldet. */
const wbFuture = makePanel(false);
wbFuture.shadowRoot._fields["wb-ts"].value = "2999-01-01T10:00";
wbFuture.shadowRoot._fields["wb-score"] = { value: "7" };
wbFuture._submitWellbeing();
const wbFutureResult = { messages: messagesOf(wbFuture), error: wbFuture._formError };

process.stdout.write(
  JSON.stringify({
    drink: drinkAfter,
    future: futureResult,
    quick: quickResult,
    bp: bpResult,
    wbStaged,
    wbConfirmed,
    wbFuture: wbFutureResult,
  })
);
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_120_panel_sends_ts_and_validates_future(tmp_path):
    """[REQ-HOM-120] Panel: ts in allen drei Schreibpfaden, Zukunft blockiert."""
    panel_copy = _prepare_panel_copy(tmp_path)
    out = json.loads(
        _run_node(tmp_path, _NODE_PANEL_TS_RUNNER, [str(panel_copy)], "runner_panel_ts")
    )

    drink = out["drink"]
    assert len(drink["messages"]) == 1
    assert drink["messages"][0]["type"] == "health_o_mat/book_drink"
    assert drink["messages"][0]["ts"]
    assert drink["draft"] == "", "das Zeitpunkt-Feld wird nach Erfolg nicht zurückgesetzt"
    assert drink["field"] != "2026-10-24T18:30"

    future = out["future"]
    assert future["messages"] == [], "ein Zukunft-Zeitpunkt wird trotzdem gebucht"
    assert "Zukunft" in future["error"]

    quick = out["quick"]
    assert quick["draft"] == quick["expected"]
    assert quick["field"] == quick["expected"], "die Schnellwahl setzt das Feld nicht"

    bp = out["bp"]
    assert len(bp["messages"]) == 1 and bp["messages"][0]["ts"]
    assert bp["messages"][0]["type"] == "health_o_mat/save_measurement"
    assert bp["draft"] == ""

    staged = out["wbStaged"]
    assert staged["sent"] == [], "die Vormerkung sendet trotz Bestätigungsmodus sofort"
    assert staged["pending"]["ts"], "die Vormerkung trägt keinen Zeitpunkt"

    confirmed = out["wbConfirmed"]
    assert len(confirmed["sent"]) == 1
    assert confirmed["sent"][0]["type"] == "health_o_mat/set_wellbeing"
    assert confirmed["sent"][0]["ts"], "die Bestätigung sendet den Zeitpunkt nicht"
    assert confirmed["pending"] is None

    wb_future = out["wbFuture"]
    assert wb_future["messages"] == []
    assert "Zukunft" in wb_future["error"]


def test_req_hom_120_panel_views_render_ts_fields_and_quick_buttons():
    """[REQ-HOM-120] Alle drei Tabs rendern `datetime-local` + Jetzt/Gestern."""
    views = _panel_views_source()

    for field in ("drink-ts", "bp-ts", "wb-ts"):
        assert f'tsFieldHtml(panel, "{field}")' in views, f"{field}-Feld fehlt im Tab"
    assert 'data-field="${field}"' in views
    assert 'data-action="${prefix}-ts-now"' in views
    assert 'data-action="${prefix}-ts-yesterday"' in views
    assert "localDateTimeValue" in views, "kein Default 'jetzt' für die Felder"


def test_req_hom_120_panel_entry_time_is_relative_then_absolute():
    """[REQ-HOM-120] Anzeige: frisch relativ, älter als 24 h absolut."""
    base = _panel_base_source()

    assert re.search(r"export\s+function\s+entryTime\s*\(", base)
    body = _js_function_block(base, "entryTime")
    assert "relativeTime(iso)" in body
    assert "24 * 60 * 60 * 1000" in body
    assert re.search(r"pad\(date\.getDate\(\)\)", body)
    assert "entryTime(" in _panel_views_source()


# --- REQ-HOM-115: Panel-Verlauf + Korrekturen (Verhalten) -------------------

_NODE_PANEL_HISTORY_RUNNER = """import { pathToFileURL } from "node:url";

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; this._fields = {}; }
  addEventListener() {}
  removeEventListener() {}
  querySelector(selector) {
    const match = /\\[data-field="([^"]+)"\\]/.exec(String(selector));
    const field = match ? match[1] : "";
    return this._fields[field] || null;
  }
  querySelectorAll() { return []; }
}

class FakeHTMLElement {
  constructor() { this._shadow = null; }
  attachShadow() { this._shadow = new FakeShadowRoot(); return this._shadow; }
  get shadowRoot() { return this._shadow; }
}

let PanelClass = null;
globalThis.HTMLElement = FakeHTMLElement;
globalThis.customElements = { get: () => undefined, define: (_n, cls) => { PanelClass = cls; } };
console.info = () => {};

await import(pathToFileURL(process.argv[2]).href);

const ENTRY = "entry-1";

function makePanel() {
  const panel = new PanelClass();
  panel._selectedEntry = ENTRY;
  panel._view = "detail";
  panel._tab = "drink";
  panel._persons = [{ entry_id: ENTRY, display_name: "Alex", person_slug: "alex" }];
  panel._data = {
    [ENTRY]: {
      areas: { drink: true, bp: true, wellbeing: true },
      undo: { drink: true, blood_pressure: true },
      wellbeing: { key: "good", at: "2026-10-19T18:00:00+02:00" },
    },
  };
  panel._busy = false;
  panel._render = () => {};
  panel._messages = [];
  panel._failVoid = false;
  panel._payloads = {
    drinks: [
      { id: "d1", ts: "2026-10-19T09:30:00+02:00", ml: 250, type: "Kaffee" },
      { id: "d0", ts: "2026-10-19T08:00:00+02:00", ml: 200, type: "Wasser",
        voided_at: "2026-10-19T10:00:00+02:00" },
    ],
    blood_pressure: [{ id: "b1", ts: "2026-10-19T07:00:00+02:00", sys: 120, dia: 80 }],
    wellbeing: [{ id: "w1", ts: "2026-10-19T18:00:00+02:00", key: "good" }],
  };
  panel._ws = async (msg) => {
    panel._messages.push(msg);
    if (msg.type === "health_o_mat/panel_data") return panel._data[msg.entry_id];
    if (msg.type === "health_o_mat/list_history") {
      const includeVoided = msg.include_voided === true;
      const all = panel._payloads[msg.kind] || [];
      return { kind: msg.kind, entries: includeVoided ? all : all.filter((e) => !e.voided_at) };
    }
    if (msg.type === "health_o_mat/void_entry" && panel._failVoid) {
      throw new Error("Server nicht erreichbar");
    }
    return { ok: true };
  };
  panel._hass = { user: { is_admin: true }, states: {}, connection: {} };
  return panel;
}

function typesOf(panel) { return panel._messages.map((msg) => msg.type); }
function lastOf(panel, type) {
  const hits = panel._messages.filter((msg) => msg.type === type);
  return hits.length ? hits[hits.length - 1] : null;
}

/* Öffnen lädt alle drei Verläufe; Default = nur aktive. */
const opened = makePanel();
await opened._openPerson(ENTRY, { silent: true });
const openedState = {
  types: typesOf(opened).filter((type) => type === "health_o_mat/list_history"),
  includes: opened._messages
    .filter((msg) => msg.type === "health_o_mat/list_history")
    .map((msg) => msg.include_voided),
  drinks: opened._history[ENTRY].drinks.entries.length,
  loaded: opened._history[ENTRY].drinks.loaded,
  canUndoDrinks: opened._canUndo(ENTRY, "drinks"),
};

/* Filter „Auch gelöscht" lädt mit include_voided neu. */
const filtered = makePanel();
await filtered._openPerson(ENTRY, { silent: true });
filtered._messages = [];
filtered._setHistoryFilter("drinks", true);
await new Promise((resolve) => setTimeout(resolve, 0));
const filterResult = {
  includeVoided: filtered._history[ENTRY].drinks.includeVoided,
  flag: filtered._historyFilter.drinks,
  message: lastOf(filtered, "health_o_mat/list_history"),
  entries: filtered._history[ENTRY].drinks.entries.length,
};

/* Inline-Bestätigung: erst der zweite Klick voidet (kein window.confirm). */
const voided = makePanel();
await voided._openPerson(ENTRY, { silent: true });
voided._messages = [];
voided._beginHistoryVoid(ENTRY, "drinks", "d1");
const beforeConfirm = { confirm: voided._historyConfirm, sent: typesOf(voided) };
await voided._confirmHistoryVoid(ENTRY, "drinks", "d1");
const afterVoid = {
  confirm: voided._historyConfirm,
  status: voided._historyStatus,
  voidMsg: lastOf(voided, "health_o_mat/void_entry"),
  reloaded: typesOf(voided).includes("health_o_mat/panel_data"),
  historyReloaded: typesOf(voided).filter((t) => t === "health_o_mat/list_history").length,
};

/* Wiederherstellen ruft restore_entry und aktualisiert. */
const restored = makePanel();
await restored._openPerson(ENTRY, { silent: true });
restored._messages = [];
await restored._setEntryVoided(ENTRY, "drinks", "d0", true);
const restoreResult = {
  msg: lastOf(restored, "health_o_mat/restore_entry"),
  status: restored._historyStatus,
};

/* Fehlerpfad: Banner-Status statt Exception. */
const failed = makePanel();
failed._failVoid = true;
await failed._openPerson(ENTRY, { silent: true });
await failed._setEntryVoided(ENTRY, "drinks", "d1", false);
const failedResult = {
  status: failed._historyStatus,
  sent: lastOf(failed, "health_o_mat/void_entry"),
};

/* Undo für BD/WB mit passendem kind. */
const undone = makePanel();
await undone._openPerson(ENTRY, { silent: true });
undone._messages = [];
await undone._undo(ENTRY, "blood_pressure");
const undoBp = lastOf(undone, "health_o_mat/undo_last");
undone._messages = [];
await undone._undo(ENTRY, "wellbeing");
const undoWb = lastOf(undone, "health_o_mat/undo_last");

process.stdout.write(JSON.stringify({
  opened: openedState,
  filter: filterResult,
  beforeConfirm,
  afterVoid,
  restore: restoreResult,
  failed: failedResult,
  undoBp,
  undoWb,
}));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_115_panel_history_flow(tmp_path):
    """[REQ-HOM-115] Laden/Filter/Void/Restore/Undo/Fehler ohne window.confirm."""
    panel_copy = _prepare_panel_copy(tmp_path)
    out = json.loads(
        _run_node(
            tmp_path,
            _NODE_PANEL_HISTORY_RUNNER,
            [str(panel_copy)],
            "runner_panel_history",
        )
    )

    opened = out["opened"]
    assert sorted(opened["types"]) == [
        "health_o_mat/list_history",
        "health_o_mat/list_history",
        "health_o_mat/list_history",
    ], "beim Öffnen werden nicht alle drei Verläufe geladen"
    assert opened["includes"] == [False, False, False], "Default ist nicht 'nur aktive'"
    assert opened["drinks"] == 1 and opened["loaded"] is True
    assert opened["canUndoDrinks"] is True

    filtered = out["filter"]
    assert filtered["flag"] is True and filtered["includeVoided"] is True
    assert filtered["message"]["include_voided"] is True, "Filter lädt nicht neu"
    assert filtered["entries"] == 2, "gelöschte Einträge fehlen nach dem Filterwechsel"

    assert out["beforeConfirm"]["confirm"] == {
        "entryId": "entry-1",
        "kind": "drinks",
        "id": "d1",
    }
    assert out["beforeConfirm"]["sent"] == [], "der erste Klick löscht sofort"
    after = out["afterVoid"]
    assert after["voidMsg"]["item_id"] == "d1"
    assert after["confirm"] is None
    assert after["status"]["ok"] is True and "gelöscht" in after["status"]["text"]
    assert after["reloaded"] is True, "panel_data wird nach Void nicht neu geladen"
    assert after["historyReloaded"] == 1, "der Verlauf wird nach Void nicht neu geladen"

    assert out["restore"]["msg"]["item_id"] == "d0"
    assert "wiederhergestellt" in out["restore"]["status"]["text"]

    assert out["failed"]["sent"]["item_id"] == "d1", "void_entry wurde nicht versucht"
    assert out["failed"]["status"]["ok"] is False
    assert "Server nicht erreichbar" in out["failed"]["status"]["text"]

    assert out["undoBp"]["kind"] == "blood_pressure"
    assert out["undoWb"]["kind"] == "wellbeing"


# --- REQ-HOM-116: Admin-Restore (Verhalten) ---------------------------------

_NODE_PANEL_RESTORE_RUNNER = """import { pathToFileURL } from "node:url";

class FakeShadowRoot {
  constructor() { this.innerHTML = ""; this._fields = {}; }
  addEventListener() {}
  removeEventListener() {}
  querySelector(selector) {
    const match = /\\[data-field="([^"]+)"\\]/.exec(String(selector));
    const field = match ? match[1] : "";
    return this._fields[field] || null;
  }
  querySelectorAll() { return []; }
}

class FakeHTMLElement {
  constructor() { this._shadow = null; }
  attachShadow() { this._shadow = new FakeShadowRoot(); return this._shadow; }
  get shadowRoot() { return this._shadow; }
}

let PanelClass = null;
globalThis.HTMLElement = FakeHTMLElement;
globalThis.customElements = { get: () => undefined, define: (_n, cls) => { PanelClass = cls; } };
console.info = () => {};

await import(pathToFileURL(process.argv[2]).href);
const admin = await import(pathToFileURL(process.argv[3]).href);

function makePanel() {
  const panel = new PanelClass();
  panel._view = "settings";
  panel._settingsEntry = "entry-1";
  panel._selectedEntry = "entry-1";
  panel._persons = [{ entry_id: "entry-1", display_name: "Alex" }];
  panel._data = { "entry-1": { areas: {} } };
  panel._settings = {};
  panel._quickDraft = [];
  panel._adminBusy = false;
  panel._settingsBusy = false;
  panel._deleteBusy = false;
  panel._render = () => {};
  panel._messages = [];
  panel._failRestore = false;
  panel._ws = async (msg) => {
    panel._messages.push(msg);
    if (panel._failRestore && msg.type === "health_o_mat/restore_backup") {
      throw new Error("Backup kaputt");
    }
    if (msg.type === "health_o_mat/list_import_files") {
      return { files: ["b_backup.json", "a_backup.json"] };
    }
    if (msg.type === "health_o_mat/list_persons") return { persons: panel._persons };
    if (msg.type === "health_o_mat/panel_data") return panel._data[msg.entry_id];
    if (msg.type === "health_o_mat/get_settings") return { daily_goal_ml: 2000 };
    if (msg.type === "health_o_mat/restore_backup") {
      return {
        plan: {
          mode: msg.mode,
          persons: { alex: "entry-1" },
          totals: { added: 3, skipped: 1, conflicts: 0, errors: 0 },
          counts: {},
          actions: [{ target: "entry-1", dataset: "drinks", op: "add", id: "d9" }],
          actions_truncated: false,
          errors: [],
          warnings: ["Zeitzone fehlt"],
          has_changes: true,
        },
        applied: !msg.dry_run,
        dry_run: !!msg.dry_run,
        backup_path: msg.dry_run ? null : "/config/health_o_mat_backup/pre.json",
      };
    }
    return {};
  };
  panel._hass = { user: { is_admin: true }, states: {}, connection: {} };
  return panel;
}

function setRestoreFields(panel, overrides) {
  const values = Object.assign({
    "restore-filename": { value: "a_backup.json" },
    "restore-mode": { value: "merge" },
    "restore-dataset-drinks": { checked: true },
    "restore-dataset-blood_pressure": { checked: true },
    "restore-dataset-wellbeing": { checked: false },
    "restore-from": { value: "2026-10-01T00:00" },
    "restore-to": { value: "2026-10-20T23:59" },
    "restore-person-map": { value: '{"alex": "entry-1"}' },
    "restore-confirm": { value: "" },
  }, overrides || {});
  panel.shadowRoot._fields = values;
}

/* Dateiliste laden (Admin-Kommando). */
const files = makePanel();
await files._loadRestoreFiles();
const fileResult = {
  files: files._restoreFiles.slice(),
  draft: files._restoreDraft.filename,
  message: files._messages.find((msg) => msg.type === "health_o_mat/list_import_files"),
};

/* Dry-Run: vollständiger Payload (Teil-Datensätze, Zeitraum, Mapping). */
const dry = makePanel();
await dry._loadRestoreFiles();
setRestoreFields(dry);
await dry._runRestore(true);
const dryMsg = dry._messages.filter((msg) => msg.type === "health_o_mat/restore_backup").pop();
const dryResult = {
  msg: dryMsg,
  result: dry._restoreResult && dry._restoreResult.dryRun,
  html: admin.restoreResultHtml(dry),
  // S-1: datetime-local → UTC-ISO (browser-lokal, daher im Runner berechnet)
  expectedFrom: new Date("2026-10-01T00:00").toISOString(),
  expectedTo: new Date("2026-10-20T23:59").toISOString(),
};

/* Replace ohne "REPLACE" wird beim Apply lokal abgelehnt. */
const blocked = makePanel();
await blocked._loadRestoreFiles();
setRestoreFields(blocked, { "restore-mode": { value: "replace" } });
await blocked._runRestore(false);
const blockedResult = {
  error: blocked._restoreError,
  sent: blocked._messages.filter((msg) => msg.type === "health_o_mat/restore_backup").length,
};

/* N-7: Replace-Dry-Run ist OHNE Bestätigung erlaubt. */
const dryReplace = makePanel();
await dryReplace._loadRestoreFiles();
setRestoreFields(dryReplace, { "restore-mode": { value: "replace" } });
await dryReplace._runRestore(true);
const dryReplaceResult = {
  error: dryReplace._restoreError,
  msg: dryReplace._messages.filter((msg) => msg.type === "health_o_mat/restore_backup").pop(),
};

/* Replace mit Bestätigung + Apply: Personen/Settings/Entries neu laden. */
const applied = makePanel();
await applied._loadRestoreFiles();
setRestoreFields(applied, {
  "restore-mode": { value: "replace" },
  "restore-confirm": { value: "REPLACE" },
});
await applied._runRestore(false);
const appliedMsg = applied._messages
  .filter((msg) => msg.type === "health_o_mat/restore_backup")
  .pop();
const appliedResult = {
  msg: appliedMsg,
  reloads: applied._messages.map((msg) => msg.type).filter((type) =>
    type === "health_o_mat/list_persons" ||
    type === "health_o_mat/panel_data" ||
    type === "health_o_mat/get_settings"),
  html: admin.restoreResultHtml(applied),
  confirm: applied._restoreDraft.confirm,
};

/* Fehlerpfad: Banner statt Crash. */
const failed = makePanel();
failed._failRestore = true;
await failed._loadRestoreFiles();
setRestoreFields(failed);
await failed._runRestore(true);
const failedResult = { error: failed._restoreError, busy: failed._restoreBusy };

/* Karte: Dateiauswahl + Ergebnis-Rendering. */
const card = makePanel();
await card._loadRestoreFiles();
card._restoreResult = {
  dryRun: true,
  data: {
    plan: {
      mode: "merge",
      persons: { alex: "entry-1" },
      totals: { added: 3, skipped: 1, conflicts: 2, errors: 0 },
      actions: [{ target: "entry-1", dataset: "drinks", op: "add" }],
      actions_truncated: true,
      warnings: ["Warnung A"],
      has_changes: true,
    },
    applied: false,
    dry_run: true,
  },
};
const cardHtml = admin.restoreCard(card);

process.stdout.write(JSON.stringify({
  files: fileResult,
  dry: dryResult,
  blocked: blockedResult,
  dryReplace: dryReplaceResult,
  applied: appliedResult,
  failed: failedResult,
  cardHtml,
}));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_116_panel_restore_flow(tmp_path):
    """[REQ-HOM-116] Dateiliste, Dry-Run-Payload, Replace-Gate, Ergebnis, Fehler."""
    panel_copy = _prepare_panel_copy(tmp_path)
    admin_copy = tmp_path / "health-o-mat-panel-admin.js"
    out = json.loads(
        _run_node(
            tmp_path,
            _NODE_PANEL_RESTORE_RUNNER,
            [str(panel_copy), str(admin_copy)],
            "runner_panel_restore",
        )
    )

    files = out["files"]
    assert files["files"] == ["b_backup.json", "a_backup.json"]
    assert files["draft"] == "b_backup.json", "die erste Datei wird nicht vorausgewählt"
    assert files["message"]["type"] == "health_o_mat/list_import_files"

    dry = out["dry"]
    msg = dry["msg"]
    assert msg["dry_run"] is True
    assert msg["filename"] == "a_backup.json"
    assert msg["mode"] == "merge"
    assert msg["datasets"] == ["drinks", "blood_pressure"]
    # S-1: `datetime-local` wird als UTC-ISO gesendet (Browser-lokale Zeit).
    assert msg["from"] == dry["expectedFrom"]
    assert msg["to"] == dry["expectedTo"]
    assert msg["from"].endswith("Z") and msg["to"].endswith("Z")
    assert msg["person_map"] == {"alex": "entry-1"}
    assert "confirm" not in msg
    assert dry["result"] is True
    assert "Dry-Run" in dry["html"]
    assert "3 hinzugefügt" in dry["html"] and "0 Konflikte" in dry["html"]
    assert "Alex" in dry["html"], "Personen-Mapping wird nicht aufgelöst"
    assert "Warnung" in dry["html"] and "Aktionen" in dry["html"]
    assert "Änderungen würden übernommen" in dry["html"]

    blocked = out["blocked"]
    assert blocked["sent"] == 0, "Replace ohne Bestätigung wird trotzdem gesendet"
    assert "REPLACE" in blocked["error"]

    # N-7: Dry-Run ist ohne Bestätigung möglich und sendet kein `confirm`.
    dry_replace = out["dryReplace"]
    assert dry_replace["error"] is None
    assert dry_replace["msg"]["mode"] == "replace"
    assert dry_replace["msg"]["dry_run"] is True
    assert "confirm" not in dry_replace["msg"]

    applied = out["applied"]
    assert applied["msg"]["mode"] == "replace"
    assert applied["msg"]["confirm"] == "REPLACE"
    assert applied["msg"]["dry_run"] is False
    assert applied["confirm"] == "", "die Bestätigung wird nach dem Apply nicht geleert"
    assert "health_o_mat/list_persons" in applied["reloads"]
    assert "health_o_mat/panel_data" in applied["reloads"]
    assert "health_o_mat/get_settings" in applied["reloads"]
    assert "Wiederhergestellt" in applied["html"]
    assert "Sicherheitsbackup" in applied["html"]

    assert "Backup kaputt" in out["failed"]["error"]
    assert out["failed"]["busy"] is False

    card_html = out["cardHtml"]
    assert 'data-action="restore-dry-run"' in card_html
    assert 'data-action="restore-apply"' in card_html
    assert 'data-action="restore-files-refresh"' in card_html
    assert "<option" in card_html and "a_backup.json" in card_html
    assert "3 hinzugefügt" in card_html
    assert "gekürzt" in card_html
    assert "Warnung A" in card_html


# --- REQ-HOM-117: HA-native UI translations (panel) ------------------------

_I18N_RUNNER = """import { pathToFileURL } from "node:url";

const base = await import(pathToFileURL(process.argv[2]).href);
const views = await import(pathToFileURL(process.argv[3]).href);
const i18n = await import(pathToFileURL(process.argv[4]).href);
const spec = JSON.parse(process.argv[5]);

async function load(language, resources, fail) {
  const hass = {
    language,
    callWS: async () => {
      if (fail) throw new Error("boom");
      return { resources: resources || {} };
    },
  };
  return i18n.loadUiTranslations(hass);
}

await load("de", {}, false);
const fallback = i18n.t("ui_card_goal", "Ziel");
const missingFallback = i18n.t("ui_missing", "Fallback {x}", { x: 7 });
const rawKey = i18n.t("ui_missing");

await load("en", spec.resources, false);
base.setUiTranslator(i18n.t);
base.setUiLanguage(i18n.currentLanguage());
const entryId = spec.panel.entry_id;
const panel = {
  _selectedEntry: entryId,
  _persons: [{ entry_id: entryId, display_name: spec.panel.display_name }],
  _data: { [entryId]: spec.panel.data },
  _entryErrors: {},
  _tab: "drink",
  _actionError: "",
  _busy: false,
  _history: {},
  _historyStatus: null,
  _historyBusy: false,
  _tsDraft: {},
  _formError: "",
  _canUndo: () => true,
  _isWarning: () => false,
  _liveValue: (data, key, fallback) => fallback,
  _liveNumber: (data, key, fallback) => fallback,
};
const english = views.renderDetail(panel);

await i18n.resetUiTranslations();
await load("en", {}, true);
const failed = i18n.t("ui_card_goal", "Ziel");

process.stdout.write(JSON.stringify({
  language: i18n.currentLanguage(),
  fallback,
  missingFallback,
  rawKey,
  english,
  failed,
}));
"""

_RESOURCES_EN = {
    "component.health_o_mat.common.ui_common_area_drink": "Drinking",
    "component.health_o_mat.common.ui_panel_drink_today": "Today",
    "component.health_o_mat.common.ui_panel_history_title": "History",
    "component.health_o_mat.common.ui_panel_drink_book": "Add",
    "component.health_o_mat.common.ui_panel_drink_quick": "Quick add",
    "component.health_o_mat.common.ui_panel_wb_question": "How are you feeling?",
    "component.health_o_mat.common.ui_common_wb_good": "Good",
}


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_117_panel_translations_load_fallback_and_language_switch(tmp_path):
    """[REQ-HOM-117] Loader-Cache, `t()`-Interpolation, Fallback und de→en-Render."""
    views_copy = _prepare_views_copy(tmp_path)
    plugin_dir = views_copy.parent
    panel = {
        "entry_id": "entry-1",
        "display_name": "Alex",
        "live_wellbeing": "unknown",
        "live_score": 4,
        "data": {
            "goal_ml": 2000,
            "areas": {"drink": True, "bp": True, "wellbeing": True},
            "entities": {},
            "today": {"ml": 500, "percent": 25, "count": 1, "breakdown": {}},
            "bp": {},
            "wellbeing": {"key": "good", "label": "Gut", "score": 4},
            "undo": {"drink": True},
        },
    }
    spec = {"resources": _RESOURCES_EN, "panel": panel}
    out = json.loads(
        _run_node(
            tmp_path,
            _I18N_RUNNER,
            [
                str(plugin_dir / "health-o-mat-panel-base.js"),
                str(views_copy),
                str(plugin_dir / "health-o-mat-i18n.js"),
                json.dumps(spec),
            ],
            "runner_i18n_panel",
        )
    )

    assert out["language"] == "en"
    assert out["fallback"] == "Ziel", "der deutsche Fallback geht verloren"
    assert out["missingFallback"] == "Fallback 7", "`{platzhalter}` wird nicht interpoliert"
    assert out["rawKey"] == "", "ein fehlender Key darf nie roh angezeigt werden"
    assert out["failed"] == "Ziel", "ein Ladefehler muss auf den Fallback zurückfallen"

    html = out["english"]
    assert "Drinking" in html, "englischer Tab-Text fehlt nach dem Sprachwechsel"
    assert "Today" in html and "History" in html, "englische Panel-Labels fehlen"
    assert "Trinken" not in html, "deutscher Tab-Text bleibt trotz en aktiv"
    assert "ui_" not in html, "roher ui_-Key im gerenderten HTML"
    assert "Gut" not in html, "das Server-Label wird nicht per Key übersetzt"


# --- REQ-HOM-122: Laborwerte im Admin-Formular ------------------------------
#
# Die Referenzdaten (`lab_catalog`, read-only aus const.py) und die drei
# Options-Felder (`lab_ref_overrides`, `lab_hidden_categories`,
# `lab_custom_markers`) kommen aus `get_settings`. Die Admin-Maske rendert
# daraus die Referenzbereich-Tabelle, die Kategorie-Checkboxen und den
# Custom-Marker-Editor; das Entry-Modul sammelt die Eingaben wieder ein.


def test_req_hom_122_panel_admin_exports_lab_settings_section():
    """[REQ-HOM-122] Die Admin-Maske exportiert den Laborwerte-Abschnitt."""
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")

    assert "export function labSettingsSection" in admin
    # Der Abschnitt wird auch tatsächlich in das Settings-Formular gespleisst.
    assert "labSettingsSection(panel, s, entryId)" in admin


def test_req_hom_122_panel_admin_lab_section_renders_hide_checkboxes():
    """[REQ-HOM-122] Je Kategorie eine Checkbox (abgewählt = ausgeblendet)."""
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")

    assert "lab-hide-" in admin
    assert "lab_custom_markers" in admin


def test_req_hom_122_panel_admin_lab_section_renders_ref_override_inputs():
    """[REQ-HOM-122] Referenzbereich je Marker ist editierbar (min/max)."""
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")

    assert "lab-ref-min-" in admin
    assert "lab-ref-max-" in admin
    assert "ref_min" in admin and "ref_max" in admin


def test_req_hom_122_panel_admin_lab_section_renders_custom_marker_form():
    """[REQ-HOM-122] Eigene Marker lassen sich anlegen und wieder entfernen."""
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")

    assert "lab-custom-add" in admin
    assert "lab-custom-remove" in admin
    assert "lab-ref-reset" in admin


def test_req_hom_122_panel_admin_lab_section_escapes_dynamic_values():
    """[REQ-HOM-122] Marker-/Kategorienamen laufen durch `escapeHtml`/`attrValue`."""
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")
    body = _js_function_block(admin, "labSettingsSection")

    assert "escapeHtml(" in body
    assert "attrValue(" in body
    assert "${marker.name_de}" not in body and "${category.name_de}" not in body, (
        "dynamische Werte werden ungeschützt interpoliert"
    )


def test_req_hom_122_panel_js_collects_lab_settings_fields():
    """[REQ-HOM-122] Das Entry-Modul sammelt alle drei Labor-Optionen ein."""
    entry = (_WWW_DIR / "health-o-mat-panel.js").read_text(encoding="utf-8")
    collect = _js_method_block(entry, "_collectSettingsPayload")
    changed = _js_method_block(entry, "_changedSettings")

    assert "lab_ref_overrides" in collect
    assert "lab_hidden_categories" in collect
    assert "lab_custom_markers" in collect
    # PATCH-Semantik: nur echte Änderungen werden gesendet.
    assert "out.lab_ref_overrides" in changed
    assert "out.lab_hidden_categories" in changed
    assert "out.lab_custom_markers" in changed


def test_req_hom_122_panel_js_has_lab_custom_draft_state():
    """[REQ-HOM-122] Der Custom-Marker-Editor hält seinen Entwurf im Speicher."""
    entry = (_WWW_DIR / "health-o-mat-panel.js").read_text(encoding="utf-8")

    assert "_labCustomDraft" in entry
    assert re.search(r"this\._labCustomDraft\s*=\s*\{\s*\}", entry), (
        "der Draft-State wird nicht initialisiert"
    )


# --- REQ-HOM-122: geteilte Labor-Rendering-Helfer im Basis-Modul ------------
#
# Panel-Tab (Task 17), Übersicht-Tile (Task 18) und Lovelace-Card (Task 19)
# zeigen dieselben Marker-Daten — Badge, Eingabe-Subzeile, Sparkline, Chart
# und Marker-Picker leben deshalb EINMAL im geteilten Basis-Modul, nicht
# dreimal kopiert.


def test_req_hom_122_panel_base_exports_lab_helpers():
    """[REQ-HOM-122] Die Labor-Helfer werden aus dem Basis-Modul exportiert."""
    text = _panel_base_source()

    for name in (
        "labBadge",
        "labReportedSubline",
        "labSparklineHtml",
        "labChartHtml",
        "labMarkerOptionsHtml",
    ):
        assert re.search(rf"export\s+function\s+{name}\s*\(", text), (
            f"{name}() fehlt im Panel-Basis-Modul"
        )


def test_req_hom_122_panel_base_lab_helpers_reuse_existing_formatters():
    """[REQ-HOM-122] Keine Duplikate: bestehende Helfer werden wiederverwendet."""
    text = _panel_base_source()

    for name in (
        "labBadge",
        "labReportedSubline",
        "labSparklineHtml",
        "labChartHtml",
        "labMarkerOptionsHtml",
    ):
        body = _js_function_block(text, name)
        assert "innerHTML" not in body, f"{name}() baut HTML ausserhalb des Helfer-Modells"

    # Dynamische Werte laufen durch die gemeinsamen Escaper/Formatter.
    assert "escapeHtml(" in _js_function_block(text, "labReportedSubline")
    assert "escapeHtml(" in _js_function_block(text, "labChartHtml")
    assert "escapeHtml(" in _js_function_block(text, "labMarkerOptionsHtml")
    assert "toNumber(" in _js_function_block(text, "labSparklineHtml")
    assert "toNumber(" in _js_function_block(text, "labChartHtml")
    assert "messageHtml(" in _js_function_block(text, "labChartHtml")


# --- REQ-HOM-122: Panel-Tab "Laborwerte" (Task 17) --------------------------
#
# Der vierte Tab laeuft ueber denselben `TABS`/`enabledTabs`-Mechanismus wie die
# drei bestehenden Tabs — eine deaktivierte `labs`-Flaeche blendet ihn aus.
# Kategorie-Wechsel laeuft ohne Gesture-Library: Klick auf die Leiste bzw.
# horizontales Wischen (touchstart/touchend) innerhalb des Tabs.


def test_req_hom_122_tabs_include_labs_entry():
    """[REQ-HOM-122] `TABS` enthaelt den vierten Eintrag fuer Laborwerte."""
    source = _panel_base_source()

    assert '"labs"' in source
    assert "ui_panel_tab_labs" in source
    # Die Flaeche muss in `AREA_KEYS` stehen, sonst ignoriert `normalizeAreas`
    # ein explizites `areas.labs = false` aus dem Backend.
    assert re.search(r'AREA_KEYS\s*=\s*\[[^\]]*"labs"', source), (
        "labs fehlt in AREA_KEYS — der Tab liesse sich nicht abschalten"
    )
    # Fehlt der Schluessel im Payload (Alt-Entry), muss die Flaeche AKTIV sein.
    normalize = _js_function_block(source, "normalizeAreas")
    assert "AREA_KEYS.forEach" in normalize
    assert "out[key] = true" in normalize, "neue Flaechen waeren per Default aus"


def test_req_hom_122_panel_views_exports_labs_tab():
    """[REQ-HOM-122] Die Views exportieren die Render-Funktion des Tabs."""
    source = _panel_views_source()

    assert "function labsTab" in source
    assert re.search(r"export\s+function\s+labsTab\s*\(", source)
    # Der Tab wird aus der bestehenden if/else-if-Kette heraus aufgerufen.
    assert 'activeTab === "labs"' in source
    assert "labsTab(panel, data, entryId)" in source


def test_req_hom_122_panel_views_renders_category_bar():
    """[REQ-HOM-122] Kategorie-Leiste mit Klick-Zielen und aktivem Zustand."""
    source = _panel_views_source()

    assert "lab-category" in source
    assert 'data-action="lab-category"' in source
    assert "lab-category-prev" in source
    assert "lab-category-next" in source
    assert "aria-selected=" in source


def test_req_hom_122_panel_views_wires_touch_swipe():
    """[REQ-HOM-122] Wischen wechselt die Kategorie (vanilla touch events)."""
    source = _panel_views_source()

    assert "touchstart" in source
    assert "touchend" in source
    # Nur im Laborwerte-Tab aktiv — andere Tabs haben kein Kategorie-Konzept.
    assert 'panel._tab !== "labs"' in source or '_tab !== "labs"' in source
    # Horizontale Geste erkennen, ohne vertikales Scrollen zu kapern.
    assert "deltaX" in source and "deltaY" in source
    assert "passive: true" in source


def test_req_hom_122_panel_views_escapes_lab_values():
    """[REQ-HOM-122] Marker-/Kategorie-Daten laufen durch `escapeHtml`."""
    source = _panel_views_source()

    row = _js_function_block(source, "labMarkerRow")
    bar = _js_function_block(source, "labCategoryBar")
    assert "escapeHtml(labDisplayName(marker, markerKey))" in row
    assert "escapeHtml(marker.unit)" in row
    assert "escapeHtml(marker.value)" in row, "der Messwert wird ungeschuetzt interpoliert"
    assert re.search(r"escapeHtml\(\s*labDisplayName\(category, category\.key\)\s*\)", bar)
    assert "labDisplayName(category, category.key)" in bar, (
        "der Kategorie-Name wird nicht sprachabhaengig aufgeloest"
    )


def test_req_hom_122_panel_views_labs_tab_hides_empty_categories():
    """[REQ-HOM-122] Versteckte/kategorielose Marker erzeugen keinen Tab-Inhalt."""
    source = _panel_views_source()

    body = _js_function_block(source, "visibleLabCategories")
    assert "category.hidden" in body
    assert "marker.category === category.key" in body
    # Leerer Zustand nutzt den gemeinsamen Message-Block.
    labs = _js_function_block(source, "labsTab")
    assert "messageHtml(" in labs
    assert "labMarkerOptionsHtml(" in labs


# --- REQ-HOM-122: Uebersicht-Kachel (Task 18) -------------------------------


def test_req_hom_122_panel_views_exports_lab_warning_count():
    """[REQ-HOM-122] Warn-Zaehler arbeitet rein auf `panel_data` (§7.3)."""
    source = _panel_views_source()

    assert "_labWarningCount" in source
    body = _js_function_block(source, "_labWarningCount")
    assert "marker.in_range === false" in body
    assert "hidden" in body
    assert "_ws(" not in body and "callWS" not in body, (
        "der Warn-Zaehler darf keinen zusaetzlichen Request ausloesen"
    )


def test_req_hom_122_panel_views_tile_shows_lab_row():
    """[REQ-HOM-122] Die Kachel zeigt eine Labor-Zeile (nur bei aktiver Flaeche)."""
    source = _panel_views_source()
    tile = _js_function_block(source, "renderTile")

    assert "lab-row-tile" in tile
    assert "areas.labs" in tile
    assert "ui_panel_tile_lab_warning" in tile
    assert "ui_panel_tile_lab_ok" in tile


def test_req_hom_122_panel_views_tile_head_badge_mentions_lab():
    """[REQ-HOM-122] Ein gemeinsames ⚠-Badge nennt beide Ursachen im Tooltip."""
    source = _panel_views_source()
    tile = _js_function_block(source, "renderTile")

    assert "ui_panel_lab_threshold_title" in tile
    # Der bestehende BD-Grund bleibt erhalten (Badge ist additiv, nie ersetzend).
    assert "ui_panel_bp_threshold_title" in tile
    assert "warn || labWarn" in tile
    assert "warnTitleParts.join" in tile


def test_req_hom_122_panel_base_export_datasets_include_lab_values():
    """[REQ-HOM-122] Das Export-Auswahlfeld spiegelt das Service-Schema inkl. `lab_values`."""
    source = _panel_base_source()

    block = re.search(r"export const EXPORT_DATASETS = \[(.*?)\];", source, re.S)
    assert block is not None, "EXPORT_DATASETS fehlt im Panel-Basis-Modul"
    entries = block.group(1)
    assert re.search(r'value:\s*"lab_values"', entries), "lab_values fehlt in EXPORT_DATASETS"
    assert "ui_common_dataset_lab_values" in entries, "eigener Label-Key fuer lab_values fehlt"
    # Bestehende Eintraege bleiben unveraendert (nur additiv erweitert).
    for value in ("all", "drinks", "blood_pressure"):
        assert re.search(rf'value:\s*"{value}"', entries), f"{value} fehlt in EXPORT_DATASETS"


# --- REQ-HOM-122: i18n der Labor-Namen ---------------------------------------
#
# `panel_data.labs` traegt seit dem E2E-Befund `name_de` UND `name_en`. Das
# Panel waehlt ueber die BESTEHENDE Sprachmechanik (`setUiLanguage`/`t`) —
# keine zweite Sprachlogik im Frontend.


def test_req_hom_122_panel_base_exports_lab_display_name():
    """[REQ-HOM-122] Sprachabhaengige Namensauflösung lebt im Basis-Modul."""
    text = _panel_base_source()

    assert re.search(r"export\s+function\s+labDisplayName\s*\(", text)
    body = _js_function_block(text, "labDisplayName")
    assert "name_en" in body and "name_de" in body
    assert "currentLanguage()" in body, "die bestehende Sprachmechanik wird nicht genutzt"


def test_req_hom_122_panel_admin_uses_localized_lab_names():
    """[REQ-HOM-122] Admin-Tabelle/-Checkboxen/-Select nutzen `labDisplayName`."""
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")
    body = _js_function_block(admin, "labSettingsSection")

    assert "labDisplayName(" in body
    assert "| hit.name_de" not in body, "Kategorie-Namen bleiben auf Deutsch hartkodiert"


_LAB_I18N_RUNNER = """import { pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const viewsPath = process.argv[2];
const views = await import(pathToFileURL(viewsPath).href);
const base = await import(
  pathToFileURL(join(dirname(viewsPath), "health-o-mat-panel-base.js")).href
);

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
const panel = { _labCategory: "", _formError: "", _busy: false };

base.setUiLanguage("de");
const german = views.labsTab(panel, { labs }, "entry-1");
base.setUiLanguage("en");
const english = views.labsTab(panel, { labs }, "entry-1");

process.stdout.write(JSON.stringify({ german, english }));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_122_panel_labs_render_german_and_english_names(tmp_path):
    """[REQ-HOM-122] Kategorie-Leiste und Marker-Zeile folgen der UI-Sprache."""
    views_copy = _prepare_views_copy(tmp_path)
    out = json.loads(
        _run_node(
            tmp_path,
            _LAB_I18N_RUNNER,
            [str(views_copy)],
            "runner_labs_i18n",
        )
    )

    assert "Leber" in out["german"] and "ALT (GPT)" in out["german"]
    assert "Liver" not in out["german"], "englischer Kategoriename erscheint im DE-Render"
    assert "Liver" in out["english"], "englischer Kategoriename fehlt im EN-Render"
    assert "ALT (ALT/GPT)" in out["english"], "englischer Marker-Name fehlt im EN-Render"
    assert "Leber" not in out["english"], "deutscher Kategoriename bleibt im EN-Render"


# --- REQ-HOM-122: Labor-Flaeche im Admin-Toggle -----------------------------

_LAB_AREA_RUNNER = """import { pathToFileURL } from "node:url";

class FakeShadowRoot {
  constructor() { this._fields = {}; }
  addEventListener() {}
  removeEventListener() {}
  querySelector(selector) {
    const match = /\\[data-field="([^"]+)"\\]/.exec(String(selector));
    const field = match ? match[1] : "";
    return this._fields[field] || null;
  }
  querySelectorAll() { return []; }
}

class FakeHTMLElement {
  constructor() { this._shadow = null; }
  attachShadow() { this._shadow = new FakeShadowRoot(); return this._shadow; }
  get shadowRoot() { return this._shadow; }
}

let PanelClass = null;
globalThis.HTMLElement = FakeHTMLElement;
globalThis.customElements = {
  get: () => undefined,
  define: (_name, cls) => { PanelClass = cls; },
};
console.info = () => {};

await import(pathToFileURL(process.argv[2]).href);

function makePanel(fields) {
  const panel = new PanelClass();
  panel.shadowRoot._fields = fields;
  return panel;
}

const full = makePanel({
  "area-drink": { checked: true },
  "area-bp": { checked: false },
  "area-wellbeing": { checked: true },
  "area-labs": { checked: false },
});
const legacy = makePanel({
  "area-drink": { checked: true },
  "area-bp": { checked: true },
  "area-wellbeing": { checked: true },
});

process.stdout.write(JSON.stringify({
  full: full._readAreaCheckboxes(),
  legacy: legacy._readAreaCheckboxes(),
}));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node nicht verfügbar")
def test_req_hom_122_panel_admin_reads_labs_area_checkbox(tmp_path):
    """[REQ-HOM-122] Die vierte Flaeche wird generisch über `AREA_KEYS` gelesen."""
    panel_copy = _prepare_panel_copy(tmp_path)
    out = json.loads(
        _run_node(
            tmp_path,
            _LAB_AREA_RUNNER,
            [str(panel_copy)],
            "runner_labs_area_toggle",
        )
    )

    assert out["full"] == {
        "drink": True,
        "bp": False,
        "wellbeing": True,
        "labs": False,
    }, "die `area-labs`-Checkbox landet nicht im Settings-Payload"
    # Alt-Payloads/aeltere DOM-Staende ohne die vierte Checkbox: Flaeche aktiv.
    assert out["legacy"]["labs"] is True, (
        "eine fehlende Checkbox darf die Labor-Flaeche nicht deaktivieren"
    )


def test_req_hom_122_panel_admin_renders_labs_area_checkbox_and_key():
    """[REQ-HOM-122] Admin-Formular rendert die Checkbox mit eigenem UI-Key."""
    admin = (_WWW_DIR / "health-o-mat-panel-admin.js").read_text(encoding="utf-8")

    assert 'data-field="area-labs"' in admin
    assert "ui_common_area_labs" in admin


# --- REQ-HOM-122: Panel-Stylesheet fuer den Labor-Tab -----------------------


def test_req_hom_122_panel_css_styles_lab_classes():
    """[REQ-HOM-122] Alle Labor-Klassen sind im Panel-Stylesheet definiert."""
    source = _panel_base_source()
    match = re.search(r"export const PANEL_CSS = `(.*?)`;", source, re.S)
    assert match is not None, "PANEL_CSS fehlt im Basis-Modul"
    css = match.group(1)

    for selector in (
        ".lab-category-bar",
        ".lab-category",
        ".lab-rows",
        ".lab-row",
        ".lab-row-value",
        ".lab-custom-list",
        ".lab-entry-form",
        ".lab-ref-table",
    ):
        assert selector in css, f"{selector} hat keine Panel-CSS-Regel"

    # Dark/Light bleibt Sache der HA-Theme-Variablen (kein eigenes Farbschema).
    for var in ("--card-background-color", "--divider-color", "--primary-color"):
        assert var in css, f"{var} wird im Labor-Stylesheet nicht wiederverwendet"

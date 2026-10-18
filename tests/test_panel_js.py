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
import os
import re
import sys
import types
from pathlib import Path

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

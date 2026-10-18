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

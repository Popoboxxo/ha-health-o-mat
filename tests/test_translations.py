"""Tests: Übersetzungs-Key-Bäume paritätisch (REQ-HOM-107, Fund N-10).

``strings.json`` ist der Master; ``translations/de.json`` und
``translations/en.json`` sind Ableitungen. REQ-HOM-107(b) verlangt, dass die
verschachtelten Key-Bäume in allen drei Dateien identisch sind — nur die Werte
dürfen sprachlich abweichen (keys-only-Vergleich).

Reiner JSON-Datei-Test: kein Home-Assistant-Import nötig.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "health_o_mat"
_MASTER = _COMPONENT_DIR / "strings.json"
_TRANSLATIONS = {
    "de": _COMPONENT_DIR / "translations" / "de.json",
    "en": _COMPONENT_DIR / "translations" / "en.json",
}

# Sektionen, die REQ-HOM-107 explizit fordert (deckt config/options/services ab).
_REQUIRED_SECTIONS = ("config", "options", "services")


def _load(path: Path) -> dict:
    """JSON-Objekt laden; die Wurzel muss ein Objekt sein."""
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data, dict), f"{path}: Wurzel ist kein JSON-Objekt"
    return data


def _all_paths(node: object, prefix: str = "") -> set[str]:
    """Alle Pfade (Knoten UND Blätter) als ``a.b.c``-Strings.

    Knoten werden mitgezählt, damit auch ein leeres Objekt (``"x": {}``) gegen
    ein fehlendes ``x`` als Abweichung erkannt wird.
    """
    paths: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{prefix}.{key}" if prefix else key
            paths.add(child)
            paths |= _all_paths(value, child)
    return paths


def _first_divergence(master: dict, other: dict) -> str | None:
    """None wenn die Key-Bäume gleich sind, sonst Meldung mit erstem Pfad."""
    master_paths = _all_paths(master)
    other_paths = _all_paths(other)
    if master_paths == other_paths:
        return None

    missing = sorted(master_paths - other_paths)
    extra = sorted(other_paths - master_paths)
    parts = []
    if missing:
        parts.append("fehlt: " + ", ".join(missing[:5]))
    if extra:
        parts.append("überzählig: " + ", ".join(extra[:5]))
    first = min(missing + extra)
    return f"erste Abweichung bei {first!r} ({'; '.join(parts)})"


@pytest.mark.parametrize("lang", sorted(_TRANSLATIONS))
def test_req_hom_107_key_tree_parity(lang: str) -> None:
    """[REQ-HOM-107] Key-Baum von translations/<lang>.json ≡ strings.json (keys-only)."""
    master = _load(_MASTER)
    other = _load(_TRANSLATIONS[lang])
    divergence = _first_divergence(master, other)
    assert divergence is None, (
        f"translations/{lang}.json weicht von strings.json ab — {divergence}"
    )


@pytest.mark.parametrize("lang", sorted(_TRANSLATIONS))
def test_req_hom_107_required_sections_present(lang: str) -> None:
    """[REQ-HOM-107] config/options/services in strings.json und <lang>.json vorhanden."""
    master = _load(_MASTER)
    other = _load(_TRANSLATIONS[lang])
    for section in _REQUIRED_SECTIONS:
        assert section in master, f"strings.json: Sektion {section!r} fehlt"
        assert section in other, f"translations/{lang}.json: Sektion {section!r} fehlt"


def test_req_hom_107_parity_helper_detects_divergence() -> None:
    """[REQ-HOM-107] Meta: der Paritäts-Helfer erkennt echte Abweichungen.

    Sichert zu, dass der Paritätstest nicht blind grün ist: fehlende,
    überzählige und leere-Objekt-Abweichungen werden alle benannt.
    """
    master = {"services": {"add_drink": {"name": "Add drink"}}}

    assert _first_divergence(master, master) is None

    missing = {"services": {}}
    assert "services.add_drink" in _first_divergence(master, missing)

    extra = {"services": {"add_drink": {"name": "Add drink"}, "bogus": {"name": "x"}}}
    assert "services.bogus" in _first_divergence(master, extra)

    # Leeres Objekt gegen fehlenden Schlüssel (nicht nur Blatt-Pfade).
    assert "a.b" in _first_divergence({"a": {}}, {"a": {"b": {}}})

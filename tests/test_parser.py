"""Tests: Freitext-Parser."""
import importlib.util
import os
import sys
import types

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket registrieren, damit relative Imports (.const) funktionieren,
# ohne das echte HA-abhängige __init__.py auszuführen.
_PKG = "_hom_test_pkg"
_pkg = types.ModuleType(_PKG)
_pkg.__path__ = [_COMPONENT_DIR]
sys.modules.setdefault(_PKG, _pkg)


def _load(name: str):
    """Lädt ein HA-freies Modul im Fake-Paketkontext."""
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.{name}", os.path.join(_COMPONENT_DIR, f"{name}.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.{name}"] = module
    spec.loader.exec_module(module)
    return module


parser = _load("parser")
logic = _load("logic")


def test_kaffee_300ml():
    r = parser.parse("Kaffee 300ml")
    assert r.ok and r.amount_ml == 300 and r.drink_type == "Kaffee"


def test_liter_komma():
    r = parser.parse("0,5 l wasser")
    assert r.ok and r.amount_ml == 500 and r.drink_type == "Wasser"


def test_nur_typ_default_menge():
    r = parser.parse("cola")
    assert r.ok and r.amount_ml == 330 and r.drink_type == "Cola"


def test_nur_zahl():
    r = parser.parse("350")
    assert r.ok and r.amount_ml == 350 and r.drink_type == "Eigen"


def test_unbekannter_typ_wortlaut():
    r = parser.parse("Ingwertee 400")
    assert r.ok and r.amount_ml == 400 and r.drink_type == "Ingwertee"


def test_unbekannter_typ_ohne_menge_fehler():
    r = parser.parse("Ingwertee")
    assert not r.ok


def test_leer():
    assert not parser.parse("").ok
    assert not parser.parse("   ").ok


def test_reihenfolge_frei():
    r = parser.parse("500ml tee")
    assert r.ok and r.amount_ml == 500 and r.drink_type == "Tee"


def test_gross_klein():
    r = parser.parse("WASSER 200 ML")
    assert r.ok and r.amount_ml == 200 and r.drink_type == "Wasser"


def test_punkt_dezimal():
    r = parser.parse("1.5 liter milch")
    assert r.ok and r.amount_ml == 1500 and r.drink_type == "Milch"


def test_zu_gross():
    r = parser.parse("wasser 99999")
    assert not r.ok


def test_null():
    assert not parser.parse("0 ml").ok

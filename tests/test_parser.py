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


# --- Konfigurierbares Getränke-Lexikon (format_lexicon/parse_lexicon_text) ---

def test_format_lexicon_parse_lexicon_text_roundtrip():
    lexicon = parser.DRINK_LEXICON
    text = parser.format_lexicon(lexicon)
    assert parser.parse_lexicon_text(text) == lexicon


def test_parse_lexicon_text_basic():
    assert parser.parse_lexicon_text("kaffee=Kaffee,250") == {"kaffee": ("Kaffee", 250)}


def test_parse_lexicon_text_ignores_comments_and_blank_lines():
    text = "# comment\n\nkaffee=Kaffee,250"
    assert parser.parse_lexicon_text(text) == {"kaffee": ("Kaffee", 250)}


def test_parse_lexicon_text_missing_ml_raises():
    try:
        parser.parse_lexicon_text("kaffee=Kaffee")
    except ValueError:
        pass
    else:
        assert False, "expected ValueError"


def test_parse_lexicon_text_ml_not_int_raises():
    try:
        parser.parse_lexicon_text("kaffee=Kaffee,abc")
    except ValueError:
        pass
    else:
        assert False, "expected ValueError"


def test_parse_lexicon_text_ml_out_of_range_raises():
    for bad in ("kaffee=Kaffee,0", "kaffee=Kaffee,20000"):
        try:
            parser.parse_lexicon_text(bad)
        except ValueError:
            pass
        else:
            assert False, f"expected ValueError for {bad!r}"


def test_parse_lexicon_text_duplicate_last_wins():
    text = "kaffee=Kaffee,250\nkaffee=Espresso,40"
    assert parser.parse_lexicon_text(text) == {"kaffee": ("Espresso", 40)}


def test_parse_lexicon_text_duplicate_different_case_normalizes_and_last_wins():
    # Wort-Normalisierung (.lower()) muss VOR dem Duplikat-Vergleich greifen,
    # sonst würden "Kaffee" und "kaffee" als zwei separate Einträge überleben.
    text = "Kaffee=Kaffee,250\nKAFFEE=Espresso,40"
    assert parser.parse_lexicon_text(text) == {"kaffee": ("Espresso", 40)}


def test_parse_lexicon_text_empty_string_returns_empty_dict():
    # Leere Options-Eingabe darf nicht crashen — Options-Flow speichert dann
    # ein leeres Lexikon (alle Worte werden fortan als unbekannter Typ behandelt).
    assert parser.parse_lexicon_text("") == {}


def test_parse_lexicon_text_only_comments_and_blank_lines_returns_empty_dict():
    text = "# nur Kommentare\n\n   \n# noch einer\n"
    assert parser.parse_lexicon_text(text) == {}


def test_parse_with_custom_lexicon_overrides_default():
    r = parser.parse("kaffee", lexicon={"kaffee": ("Espresso", 40)})
    assert r.ok and r.drink_type == "Espresso" and r.amount_ml == 40


def test_parse_without_lexicon_arg_unchanged_regression():
    # Regression guard: Aufruf ohne `lexicon` verhält sich exakt wie vorher.
    r = parser.parse("kaffee 300ml")
    assert r.ok and r.amount_ml == 300 and r.drink_type == "Kaffee"

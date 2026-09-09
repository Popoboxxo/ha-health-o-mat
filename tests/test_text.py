"""Tests: FreeTextDrinkEntity — konfigurierbares Getränke-Lexikon (on-read)."""
import asyncio
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket für relative Imports
_PKG = "_hom_test_pkg"
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


text_module = _load("text")


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_entity(options: dict):
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = options
    store = MagicMock()
    store.add_drink = AsyncMock()
    entity = text_module.FreeTextDrinkEntity(coordinator, entry, store)
    entity.hass = MagicMock()
    return entity, entry, store


def test_async_set_value_resolves_custom_lexicon_word():
    """[Spec Feature 1 - AC 11] Wort, das nur im custom drink_lexicon steckt, wird erkannt."""
    entity, entry, store = _make_entity({"drink_lexicon": {"matecha": ("Matcha-Tee", 300)}})

    _run(entity.async_set_value("matecha"))

    store.add_drink.assert_called_once()
    args = store.add_drink.call_args[0]
    assert args[2] == 300  # amount_ml
    assert args[3] == "Matcha-Tee"  # drink_type


def test_async_set_value_falls_back_to_default_lexicon_without_options():
    """Ohne entry.options['drink_lexicon'] gilt weiterhin DRINK_LEXICON (Default)."""
    entity, entry, store = _make_entity({})

    _run(entity.async_set_value("kaffee 300ml"))

    store.add_drink.assert_called_once()
    args = store.add_drink.call_args[0]
    assert args[2] == 300
    assert args[3] == "Kaffee"

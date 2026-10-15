"""Tests: ui_store.py — Per-User-UI-Einstellungen (Persistenz/Defaults/get/set).

Läuft ohne Home-Assistant-Runtime: der HA-`Store` wird durch einen kleinen,
zustandsbehaltenden Fake ersetzt (Patch im Modul-Namespace, weil `ui_store`
`Store` bereits beim Import gebunden hat).
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket für relative Imports
_PKG = "_hom_ui_store_test_pkg"
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


ui_store = _load("ui_store")


class FakeStore:
    """Zustandsbehaltender Ersatz für homeassistant.helpers.storage.Store."""

    def __init__(self, initial: dict | None = None) -> None:
        self.data = initial
        self.saves: list[dict] = []

    async def async_load(self):
        return self.data

    async def async_save(self, data) -> None:
        self.data = data
        self.saves.append(data)


def _make(monkeypatch, initial: dict | None = None) -> tuple:
    fake = FakeStore(initial)
    monkeypatch.setattr(ui_store, "Store", MagicMock(return_value=fake))
    return ui_store.HealthOMatUiStore(MagicMock()), fake


# --- Reine Merge-/Default-Logik (HA-frei) ----------------------------------


def test_default_ui_settings_structure():
    """Defaults: selected_person None, leere prefs — frische Referenzen."""
    first = ui_store.default_ui_settings()
    second = ui_store.default_ui_settings()
    assert first == {"selected_person": None, "prefs": {}}
    assert first is not second
    assert first["prefs"] is not second["prefs"]


def test_merge_ui_settings_defaults_and_updates():
    """Defaults + Updates werden zu einer Struktur gemergt."""
    merged = ui_store.merge_ui_settings(None, {"selected_person": "entry-1"})
    assert merged == {"selected_person": "entry-1", "prefs": {}}

    merged = ui_store.merge_ui_settings(
        {"selected_person": "entry-1"}, {"prefs": {"compact": True}}
    )
    assert merged["selected_person"] == "entry-1"
    assert merged["prefs"] == {"compact": True}


def test_merge_ui_settings_prefs_merge_shallow():
    """prefs wird flach gemergt — Alt-Werte bleiben, Neues überschreibt."""
    merged = ui_store.merge_ui_settings(
        {"selected_person": "e1", "prefs": {"theme": "dark", "compact": False}},
        {"prefs": {"compact": True}},
    )
    assert merged["prefs"] == {"theme": "dark", "compact": True}


def test_merge_ui_settings_drops_unknown_keys():
    """Whitelist: unbekannte Schlüssel (und damit Gesundheitsdaten) fallen weg."""
    merged = ui_store.merge_ui_settings(
        {"selected_person": "e1", "last_reading": {"sys": 120}},
        {"diastolic": 80, "prefs": {"compact": True}},
    )
    assert set(merged) == {"selected_person", "prefs"}
    assert "last_reading" not in merged
    assert "diastolic" not in merged


def test_merge_ui_settings_selected_person_normalized():
    """Nicht-String selected_person wird zu None (kaputte Daten bleiben harmlos)."""
    assert ui_store.merge_ui_settings({"selected_person": 42}, {})["selected_person"] is None
    assert (
        ui_store.merge_ui_settings({"selected_person": "e1"}, {"selected_person": None})[
            "selected_person"
        ]
        is None
    )


# --- Store-Verhalten --------------------------------------------------------


def test_get_unknown_user_returns_defaults(monkeypatch):
    """Unbekannter Nutzer → Defaults (kein Fehler, frische Kopie)."""
    store, _ = _make(monkeypatch)
    asyncio.run(store.async_load())

    assert store.get("nobody") == {"selected_person": None, "prefs": {}}
    assert store.get(None) == {"selected_person": None, "prefs": {}}


def test_set_selected_person_persists_and_returns(monkeypatch):
    """async_set persistiert user_id → selected_person und liefert das Ergebnis."""
    store, fake = _make(monkeypatch)
    asyncio.run(store.async_load())

    result = asyncio.run(store.async_set("user-1", selected_person="entry-a"))

    assert result == {"selected_person": "entry-a", "prefs": {}}
    assert store.get("user-1")["selected_person"] == "entry-a"
    assert fake.data == {"users": {"user-1": {"selected_person": "entry-a", "prefs": {}}}}
    assert fake.saves  # es wurde tatsächlich gespeichert


def test_set_prefs_merges_across_calls(monkeypatch):
    """Mehrere async_set-Aufrufe mergen (prefs bleiben erhalten)."""
    store, _ = _make(monkeypatch)
    asyncio.run(store.async_load())

    asyncio.run(store.async_set("user-1", selected_person="entry-a"))
    asyncio.run(store.async_set("user-1", prefs={"compact": True}))
    asyncio.run(store.async_set("user-1", prefs={"theme": "dark"}))

    settings = store.get("user-1")
    assert settings["selected_person"] == "entry-a"
    assert settings["prefs"] == {"compact": True, "theme": "dark"}


def test_reload_restores_persisted_settings(monkeypatch):
    """Neu geladen aus demselben Store → Einstellungen sind zurück."""
    fake = FakeStore()
    monkeypatch.setattr(ui_store, "Store", MagicMock(return_value=fake))

    first = ui_store.HealthOMatUiStore(MagicMock())
    asyncio.run(first.async_load())
    asyncio.run(first.async_set("user-1", selected_person="entry-a", prefs={"compact": True}))

    second = ui_store.HealthOMatUiStore(MagicMock())
    asyncio.run(second.async_load())

    assert second.get("user-1") == {"selected_person": "entry-a", "prefs": {"compact": True}}


def test_get_returns_isolated_copy(monkeypatch):
    """Mutieren des Ergebnisses verändert den gespeicherten Zustand nicht."""
    store, _ = _make(monkeypatch)
    asyncio.run(store.async_load())
    asyncio.run(store.async_set("user-1", selected_person="entry-a"))

    got = store.get("user-1")
    got["selected_person"] = "hacked"
    got["prefs"]["compact"] = True

    assert store.get("user-1") == {"selected_person": "entry-a", "prefs": {}}


def test_load_handles_missing_and_corrupt_data(monkeypatch):
    """Kein Store-Inhalt bzw. kaputte Nutzer-Struktur → leerer Start ohne Fehler."""
    for initial in (None, {}, {"users": "not-a-dict"}, {"users": {"u": "not-a-dict"}}):
        store, _ = _make(monkeypatch, initial)
        asyncio.run(store.async_load())
        assert store.all_users() == {}


def test_all_users_returns_copies(monkeypatch):
    """all_users() liefert Kopien (Diagnostics/Tests verändern nichts)."""
    store, _ = _make(monkeypatch)
    asyncio.run(store.async_load())
    asyncio.run(store.async_set("user-1", selected_person="entry-a"))

    snapshot = store.all_users()
    snapshot["user-1"]["selected_person"] = "mutated"

    assert store.get("user-1")["selected_person"] == "entry-a"

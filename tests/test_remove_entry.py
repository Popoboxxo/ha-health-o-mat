"""Tests: `async_remove_entry` räumt die Langzeitstatistik auf (Befund 2).

Beim Entfernen eines Config-Entry über ``DELETE`` leert HA nur die Entity-
Registry — die ``statistics_meta``-Zeilen der Entities bleiben stehen und
``recorder.purge_entities`` entfernt sie nicht. ``async_remove_entry`` muss die
Statistik-IDs deshalb selbst aufräumen, und zwar defensiv: ohne Recorder (nicht
eingerichtet/deaktiviert) oder ohne die API in der installierten HA-Version darf
das Entfernen der Integration nicht scheitern.

``__init__.py`` wird wie in ``tests/test_entry_migration.py`` über importlib
geladen (eigenes Paket-Präfix, damit die Modul-Caches nicht kollidieren). Die
Recorder-Module werden pro Test über ``sys.modules`` ersetzt — die Imports im
Produktivcode sind lazy, damit ist der Pfad exakt der Laufzeitpfad.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)
_PKG = "_hom_remove_entry_pkg"
_pkg = types.ModuleType(_PKG)
_pkg.__path__ = [_COMPONENT_DIR]
sys.modules.setdefault(_PKG, _pkg)

ENTRY_ID = "01JENTRY"

_RECORDER_MODULE = "homeassistant.components.recorder"
_RECORDER_STATISTICS_MODULE = "homeassistant.components.recorder.statistics"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.{name}", os.path.join(_COMPONENT_DIR, f"{name}.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.{name}"] = module
    spec.loader.exec_module(module)
    return module


def _load_init():
    """Integrationsmodul laden (relativer Import über das Fake-Paket)."""
    spec = importlib.util.spec_from_file_location(
        f"{_PKG}.init", os.path.join(_COMPONENT_DIR, "__init__.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.init"] = module
    spec.loader.exec_module(module)
    return module


hom_init = _load_init()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _entry(entity_ids: list[str]) -> SimpleNamespace:
    return SimpleNamespace(entry_id=ENTRY_ID, title="Max", options={}, data={"person": "max"})


def _install_registry(monkeypatch, entity_ids: list[str]) -> None:
    """Entity-Registry des Integrationsmoduls auf eine feste ID-Liste patchen."""
    entries = [
        SimpleNamespace(entity_id=entity_id, unique_id=entity_id) for entity_id in entity_ids
    ]
    monkeypatch.setattr(hom_init.er, "async_get", lambda hass: "registry")
    monkeypatch.setattr(
        hom_init.er, "async_entries_for_config_entry", lambda registry, entry_id: list(entries)
    )


def _install_instance_recorder(monkeypatch) -> MagicMock:
    """Recorder-Instanz-API installieren; Rückgabe verfolgt die Aufrufe."""
    instance = MagicMock(name="recorder_instance")
    recorder_module = types.ModuleType(_RECORDER_MODULE)
    recorder_module.get_instance = lambda hass: instance
    monkeypatch.setitem(sys.modules, _RECORDER_MODULE, recorder_module)
    # Modul-API in dieser HA-Version nicht vorhanden (2026.2.3).
    monkeypatch.setitem(sys.modules, _RECORDER_STATISTICS_MODULE, None)
    return instance


def _install_module_recorder(monkeypatch, clear: AsyncMock) -> None:
    """Modul-API ``async_clear_statistics`` in ``recorder.statistics`` installieren."""
    statistics_module = types.ModuleType(_RECORDER_STATISTICS_MODULE)
    statistics_module.async_clear_statistics = clear
    monkeypatch.setitem(sys.modules, _RECORDER_STATISTICS_MODULE, statistics_module)


def _run_remove(entry=None):
    return asyncio.run(hom_init.async_remove_entry(MagicMock(name="hass"), entry or _entry([])))


# ---------------------------------------------------------------------------
# Befund 2 — Statistik-Cleanup beim Entfernen des Entrys
# ---------------------------------------------------------------------------


def test_remove_entry_clears_statistics_for_entry_entities(monkeypatch):
    """[Befund 2] Alle Entity-IDs des Entrys werden der Recorder-API übergeben."""
    entity_ids = [
        "sensor.health_o_mat_max_drinks_today",
        "sensor.health_o_mat_max_lifetime_total",
        "binary_sensor.health_o_mat_max_goal_reached",
    ]
    _install_registry(monkeypatch, entity_ids)
    instance = _install_instance_recorder(monkeypatch)

    _run_remove(_entry(entity_ids))

    instance.async_clear_statistics.assert_called_once_with(sorted(entity_ids))


def test_remove_entry_prefers_module_level_statistics_api(monkeypatch):
    """[Befund 2] Modul-API (falls vorhanden) wird bevorzugt und awaited."""
    _install_registry(monkeypatch, ["sensor.health_o_mat_max_drinks_today"])
    instance = _install_instance_recorder(monkeypatch)
    clear = AsyncMock(name="module_clear_statistics")
    _install_module_recorder(monkeypatch, clear)

    _run_remove()

    clear.assert_awaited_once()
    called_ids = clear.await_args.args[-1]
    assert called_ids == ["sensor.health_o_mat_max_drinks_today"]
    instance.async_clear_statistics.assert_not_called()


def test_remove_entry_without_recorder_does_not_raise(monkeypatch):
    """[Befund 2] Ohne Recorder-API: keine Ausnahme, Cleanup still übersprungen."""
    _install_registry(monkeypatch, ["sensor.health_o_mat_max_drinks_today"])
    # Beide Importe scheitern — genau der Fall "Recorder nicht installiert".
    monkeypatch.setitem(sys.modules, _RECORDER_STATISTICS_MODULE, None)
    monkeypatch.setitem(sys.modules, _RECORDER_MODULE, None)

    _run_remove()  # darf nicht werfen


def test_remove_entry_survives_recorder_failure(monkeypatch):
    """[Befund 2] Fehler der Recorder-API bricht das Entfernen nicht ab."""
    _install_registry(monkeypatch, ["sensor.health_o_mat_max_drinks_today"])
    instance = _install_instance_recorder(monkeypatch)
    instance.async_clear_statistics.side_effect = RuntimeError("recorder down")

    _run_remove()  # darf nicht werfen


def test_remove_entry_is_noop_without_entities(monkeypatch):
    """[Befund 2] Ohne Registry-Einträge wird der Recorder gar nicht berührt."""
    _install_registry(monkeypatch, [])
    instance = _install_instance_recorder(monkeypatch)

    _run_remove()

    instance.async_clear_statistics.assert_not_called()


def test_remove_entry_is_noop_without_registry(monkeypatch):
    """[Befund 2] Unlesbare Registry: definierter No-op statt Ausnahme."""
    monkeypatch.setattr(hom_init.er, "async_get", MagicMock(side_effect=RuntimeError("boom")))
    instance = _install_instance_recorder(monkeypatch)

    _run_remove()

    instance.async_clear_statistics.assert_not_called()

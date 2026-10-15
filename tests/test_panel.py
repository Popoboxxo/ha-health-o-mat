"""Tests: panel.py — Opt-in-Sidebar-Panel, idempotent und unload-sicher.

Läuft ohne Home-Assistant-Runtime: `hass` ist ein minimaler Fake (nur `data`);
`panel_custom.async_register_panel` und `frontend.async_remove_panel` werden
durch aufzeichnende Fakes ersetzt. So werden Registrierung, Parameter,
Idempotenz und Rückbau ehrlich beobachtbar statt weg-gemockt.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from types import SimpleNamespace

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket für relative Imports
_PKG = "_hom_panel_test_pkg"
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


panel = _load("panel")

DOMAIN = "health_o_mat"


class FakeHass:
    """Minimaler Hass-Ersatz: nur `data` wird benutzt."""

    def __init__(self) -> None:
        self.data: dict = {}


class FakePanelCustom:
    """Zeichnet Panel-Registrierungen auf (Kern-API der installierten HA-Version)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def async_register_panel(self, hass, **kwargs) -> None:
        self.calls.append(kwargs)


class FakeRemove:
    """Aufzeichnender Ersatz für `frontend.async_remove_panel` (synchron)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def __call__(self, hass, frontend_url_path: str, *, warn_if_unknown: bool = True) -> None:
        self.calls.append((frontend_url_path, warn_if_unknown))


def _patch(monkeypatch) -> tuple[FakePanelCustom, FakeRemove]:
    fake_panel = FakePanelCustom()
    fake_remove = FakeRemove()
    monkeypatch.setattr(panel, "panel_custom", fake_panel)
    monkeypatch.setattr(panel, "async_remove_panel", fake_remove)
    return fake_panel, fake_remove


def _entry(options: dict | None = None):
    return SimpleNamespace(options=options or {})


# --- Opt-in-Auswertung (HA-frei) -------------------------------------------


def test_panel_enabled_defaults_off():
    """[CONCEPT-UI §8.3] Ohne/mit falscher Option ist das Panel AUS (Default)."""
    assert panel.panel_enabled(None) is False
    assert panel.panel_enabled({}) is False
    assert panel.panel_enabled({panel.OPTION_ENABLE_SIDEBAR_PANEL: False}) is False
    assert panel.panel_enabled({panel.OPTION_ENABLE_SIDEBAR_PANEL: True}) is True


def test_panel_requested_true_when_any_entry_enables():
    """Mehrere Entries: ein einziges aktives Opt-in genügt für das EINE Panel."""
    assert panel.panel_requested([]) is False
    assert panel.panel_requested([_entry({}), _entry({})]) is False
    assert panel.panel_requested([_entry({}), _entry({panel.OPTION_ENABLE_SIDEBAR_PANEL: True})])


def test_panel_urls_are_consistent():
    """[§5.1] Modul-URL zeigt auf dieselbe www-Auslieferung wie die Card."""
    assert panel.PANEL_URL_PATH == "health-o-mat"
    assert panel.WEBCOMPONENT_NAME == "health-o-mat-panel"
    assert panel.PANEL_MODULE_URL == f"{panel.URL_BASE}/health-o-mat-panel.js"
    assert panel.PANEL_MODULE_URL == "/health_o_mat/health-o-mat-panel.js"


# --- Registrierung ----------------------------------------------------------


def test_setup_registers_panel_with_expected_params(monkeypatch):
    """Registrierung nutzt exakt die Parameter der installierten HA-Signatur."""
    fake_panel, _ = _patch(monkeypatch)
    hass = FakeHass()

    asyncio.run(panel.async_setup_panel(hass))

    assert len(fake_panel.calls) == 1
    call = fake_panel.calls[0]
    assert call["frontend_url_path"] == "health-o-mat"
    assert call["webcomponent_name"] == "health-o-mat-panel"
    assert call["sidebar_title"] == "Health-O-Mat"
    assert call["sidebar_icon"] == "mdi:heart-pulse"
    assert call["module_url"] == "/health_o_mat/health-o-mat-panel.js"
    assert call["require_admin"] is False
    assert call["config"] == {}


def test_setup_is_idempotent(monkeypatch):
    """Zweiter Aufruf erzeugt KEINE Doppel-Registrierung (Marker)."""
    fake_panel, _ = _patch(monkeypatch)
    hass = FakeHass()

    asyncio.run(panel.async_setup_panel(hass))
    asyncio.run(panel.async_setup_panel(hass))

    assert len(fake_panel.calls) == 1


def test_multiple_entries_register_panel_only_once(monkeypatch):
    """Mehrere (opt-in) Entries → genau EIN Sidebar-Panel."""
    fake_panel, _ = _patch(monkeypatch)
    hass = FakeHass()
    entries = [_entry({panel.OPTION_ENABLE_SIDEBAR_PANEL: True}) for _ in range(3)]

    asyncio.run(panel.async_apply_panel_state(hass, entries))

    assert len(fake_panel.calls) == 1


def test_apply_state_off_does_not_register(monkeypatch):
    """Opt-in AUS: kein Panel registriert."""
    fake_panel, fake_remove = _patch(monkeypatch)
    hass = FakeHass()

    applied = asyncio.run(panel.async_apply_panel_state(hass, [_entry({})]))

    assert applied is False
    assert fake_panel.calls == []
    assert fake_remove.calls == []  # war nie registriert → kein Entfernen


def test_apply_state_on_registers(monkeypatch):
    """Opt-in AN: Panel registriert."""
    fake_panel, _ = _patch(monkeypatch)
    hass = FakeHass()

    applied = asyncio.run(
        panel.async_apply_panel_state(hass, [_entry({panel.OPTION_ENABLE_SIDEBAR_PANEL: True})])
    )

    assert applied is True
    assert len(fake_panel.calls) == 1


# --- Rückbau ----------------------------------------------------------------


def test_unregister_removes_registered_panel_once(monkeypatch):
    """Rückbau entfernt das Panel und ist idempotent (kein zweites Entfernen)."""
    fake_panel, fake_remove = _patch(monkeypatch)
    hass = FakeHass()

    asyncio.run(panel.async_setup_panel(hass))
    asyncio.run(panel.async_unregister_panel(hass))
    asyncio.run(panel.async_unregister_panel(hass))

    assert fake_remove.calls == [("health-o-mat", False)]
    assert len(fake_panel.calls) == 1


def test_apply_state_off_unregisters_after_enable(monkeypatch):
    """enable → disable entfernt das Panel wieder (Options-Wechsel)."""
    fake_panel, fake_remove = _patch(monkeypatch)
    hass = FakeHass()
    enabled = _entry({panel.OPTION_ENABLE_SIDEBAR_PANEL: True})

    asyncio.run(panel.async_apply_panel_state(hass, [enabled]))
    assert len(fake_panel.calls) == 1

    asyncio.run(panel.async_apply_panel_state(hass, [_entry({})]))
    assert fake_remove.calls == [("health-o-mat", False)]


def test_setup_defensive_when_panel_custom_missing(monkeypatch):
    """Fehlende Panel-Komponente: kein Crash, kein Marker (späterer Retry möglich)."""
    _patch(monkeypatch)
    monkeypatch.setattr(panel, "panel_custom", None)
    hass = FakeHass()

    asyncio.run(panel.async_setup_panel(hass))

    assert panel.shared_data(hass).get("panel_registered") is None


def test_setup_defensive_when_registration_raises(monkeypatch):
    """Wirft die Registrierung, bleibt das Setup ohne Exception und ohne Marker."""
    _, _ = _patch(monkeypatch)
    hass = FakeHass()

    class Boom:
        async def async_register_panel(self, *args, **kwargs):
            raise RuntimeError("panel_custom broken")

    monkeypatch.setattr(panel, "panel_custom", Boom())

    asyncio.run(panel.async_setup_panel(hass))

    assert panel.shared_data(hass).get("panel_registered") is None

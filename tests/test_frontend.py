"""Tests: frontend.py — statischer Pfad + idempotente Card-Registrierung.

Läuft ohne Home-Assistant-Runtime: `hass` ist ein minimaler Fake (nur `data`
+ `http`), die HA-Hilfsfunktionen (StaticPathConfig, add/remove_extra_js_url)
sind die echten — sie arbeiten ausschließlich auf `hass.data`, sodass die
Registrierung ehrlich beobachtbar wird statt weg-gemockt zu werden.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from types import SimpleNamespace

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)

# Fake-Paket für relative Imports
_PKG = "_hom_frontend_test_pkg"
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

DOMAIN = "health_o_mat"


class FakeHttp:
    """Minimales `hass.http` — zeichnet statische Pfad-Registrierungen auf."""

    def __init__(self) -> None:
        self.registered: list[list] = []

    async def async_register_static_paths(self, configs) -> None:
        self.registered.append(list(configs))


class FakeHass:
    """Minimaler Hass-Ersatz: nur `data` und `http` werden benutzt."""

    def __init__(self) -> None:
        self.data: dict = {}
        self.http = FakeHttp()


class FakeResources:
    """Lovelace-Ressourcen-Collection im Storage-Modus (Duck-Typing-API)."""

    def __init__(self, items: list[dict] | None = None, loaded: bool = True) -> None:
        self.items = list(items or [])
        self.loaded = loaded
        self.load_calls = 0
        self.created: list[dict] = []
        self.updated: list[tuple] = []

    async def async_load(self) -> None:
        self.load_calls += 1

    def async_items(self) -> list[dict]:
        return list(self.items)

    async def async_create_item(self, data: dict) -> dict:
        self.created.append(data)
        item = {"id": "new", "type": data.get("res_type"), "url": data["url"]}
        self.items.append(item)
        return item

    async def async_update_item(self, item_id: str, updates: dict) -> dict:
        self.updated.append((item_id, dict(updates)))
        for item in self.items:
            if item.get("id") == item_id:
                item.update(updates)
        return next(item for item in self.items if item.get("id") == item_id)


class FakeYamlResources:
    """Lovelace-Ressourcen im YAML-Modus: nicht beschreibbar."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def async_items(self) -> list[dict]:
        return list(self.items)


def _with_lovelace(hass: FakeHass, resources) -> None:
    from homeassistant.components.lovelace.const import LOVELACE_DATA

    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources)


def _with_extra_js_store(hass: FakeHass) -> None:
    hass.data[DATA_EXTRA_MODULE_URL] = set()


def test_static_path_registered_once_with_expected_config(tmp_path, monkeypatch):
    """Statischer Pfad: URL_BASE, www-Verzeichnis, cache_headers — genau einmal."""
    monkeypatch.setattr(frontend, "WWW_DIR", tmp_path)
    hass = FakeHass()
    resources = FakeResources()
    _with_lovelace(hass, resources)

    asyncio.run(frontend.async_setup_frontend(hass))
    asyncio.run(frontend.async_setup_frontend(hass))

    assert len(hass.http.registered) == 1, "Doppelregistrierung trotz Marker"
    config = hass.http.registered[0][0]
    assert config.url_path == "/health_o_mat"
    assert config.path == str(tmp_path)
    assert config.cache_headers is True
    assert frontend.CARD_URL == (
        f"/health_o_mat/health-o-mat-card.js?v={frontend.integration_version()}"
    )


def test_card_resource_registered_as_lovelace_resource(tmp_path, monkeypatch):
    """Storage-Modus: Card landet als Module-Ressource — und nur einmal."""
    monkeypatch.setattr(frontend, "WWW_DIR", tmp_path)
    hass = FakeHass()
    resources = FakeResources()
    _with_lovelace(hass, resources)
    _with_extra_js_store(hass)

    asyncio.run(frontend.async_setup_frontend(hass))
    asyncio.run(frontend.async_setup_frontend(hass))

    assert resources.created == [{"res_type": "module", "url": frontend.CARD_URL}]
    # Kein Fallback, wenn die Lovelace-Ressource greift (sonst Doppel-Laden).
    assert hass.data[DATA_EXTRA_MODULE_URL] == set()


def test_lovelace_resource_loaded_lazily_when_not_loaded(tmp_path, monkeypatch):
    """Nicht geladene Collection wird vor der Dedupe-Prüfung geladen."""
    monkeypatch.setattr(frontend, "WWW_DIR", tmp_path)
    hass = FakeHass()
    resources = FakeResources(loaded=False)
    _with_lovelace(hass, resources)

    asyncio.run(frontend.async_setup_frontend(hass))

    assert resources.load_calls == 1
    assert resources.created and resources.loaded is True


def test_existing_card_resource_is_deduped(tmp_path, monkeypatch):
    """Bereits vorhandene Card (plain ODER versioniert) wird nicht erneut angelegt."""
    monkeypatch.setattr(frontend, "WWW_DIR", tmp_path)
    hass = FakeHass()
    # Unversionierte Alt-URL und eine versionierte URL mit anderem Cache-Buster
    # müssen BEIDE als dieselbe Card erkannt werden.
    resources = FakeResources(
        items=[
            {"url": frontend.CARD_BASE_URL},
            {"url": f"{frontend.CARD_BASE_URL}?v=0"},
        ]
    )
    _with_lovelace(hass, resources)

    asyncio.run(frontend.async_setup_frontend(hass))

    assert resources.created == []


def test_versioned_card_url_is_recognised_as_the_same_card(tmp_path, monkeypatch):
    """Die eigene (versionierte) URL dedupliziert gegen die unversionierte Form."""
    monkeypatch.setattr(frontend, "WWW_DIR", tmp_path)
    hass = FakeHass()
    resources = FakeResources(items=[{"url": frontend.CARD_URL}])
    _with_lovelace(hass, resources)

    asyncio.run(frontend.async_setup_frontend(hass))

    assert resources.created == []


def test_existing_unversioned_resource_is_refreshed(tmp_path, monkeypatch):
    """Bestands-Ressource ohne `?v=` wird auf die aktuelle versionierte URL gezogen."""
    monkeypatch.setattr(frontend, "WWW_DIR", tmp_path)
    hass = FakeHass()
    resources = FakeResources(
        items=[{"id": "abc", "type": "module", "url": frontend.CARD_BASE_URL}]
    )
    _with_lovelace(hass, resources)

    asyncio.run(frontend.async_setup_frontend(hass))

    assert resources.created == []
    assert resources.updated == [("abc", {"url": frontend.CARD_URL})]
    assert resources.items[0]["url"] == frontend.CARD_URL


def test_existing_current_resource_is_not_refreshed(tmp_path, monkeypatch):
    """Bereits aktuelle URL → kein Update (idempotent, kein Storage-Schreibvorgang)."""
    monkeypatch.setattr(frontend, "WWW_DIR", tmp_path)
    hass = FakeHass()
    resources = FakeResources(items=[{"id": "abc", "type": "module", "url": frontend.CARD_URL}])
    _with_lovelace(hass, resources)

    asyncio.run(frontend.async_setup_frontend(hass))

    assert resources.created == []
    assert resources.updated == []


def test_versioned_url_and_integration_version(tmp_path, monkeypatch):
    """`versioned_url` hängt die Integrationsversion an und bestätigt CARD_URL."""
    assert frontend.versioned_url("x.js") == (
        f"/health_o_mat/x.js?v={frontend.integration_version()}"
    )
    assert frontend.CARD_URL == frontend.versioned_url(frontend.CARD_FILENAME)


def test_integration_version_falls_back_when_manifest_unreadable(monkeypatch, tmp_path):
    """Unlesbare `manifest.json` → `"0"` statt Exception (defensiv)."""
    monkeypatch.setattr(frontend, "_VERSION", None)
    monkeypatch.setattr(frontend, "_MANIFEST_PATH", tmp_path / "missing.json")

    assert frontend.integration_version() == "0"

    monkeypatch.setattr(frontend, "_VERSION", None)
    bad = tmp_path / "manifest.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(frontend, "_MANIFEST_PATH", bad)

    assert frontend.integration_version() == "0"


def test_missing_www_dir_skips_static_path_and_recovers(tmp_path, monkeypatch):
    """Fehlendes www/: kein Crash, kein Marker — späterer Aufruf registriert nach."""
    missing = tmp_path / "www"
    monkeypatch.setattr(frontend, "WWW_DIR", missing)
    hass = FakeHass()

    asyncio.run(frontend.async_setup_frontend(hass))

    assert hass.http.registered == []
    assert frontend.shared_data(hass).get("frontend_static_path") is None

    # Verzeichnis taucht auf (z. B. Sync ohne Neustart) → selbstheilende Registrierung
    missing.mkdir()
    asyncio.run(frontend.async_setup_frontend(hass))
    assert len(hass.http.registered) == 1


def test_fallback_to_extra_js_without_lovelace(tmp_path, monkeypatch):
    """Ohne Lovelace-Datenstruktur wird `add_extra_js_url` als Fallback benutzt."""
    monkeypatch.setattr(frontend, "WWW_DIR", tmp_path)
    hass = FakeHass()
    _with_extra_js_store(hass)

    asyncio.run(frontend.async_setup_frontend(hass))
    asyncio.run(frontend.async_setup_frontend(hass))

    assert hass.data[DATA_EXTRA_MODULE_URL] == {frontend.CARD_URL}
    assert frontend.shared_data(hass)["frontend_card_registered"] == "extra_js"


def test_fallback_when_lovelace_is_yaml_mode(tmp_path, monkeypatch):
    """YAML-Ressourcenmodus ist nicht schreibbar → Fallback statt Fehler."""
    monkeypatch.setattr(frontend, "WWW_DIR", tmp_path)
    hass = FakeHass()
    _with_lovelace(hass, FakeYamlResources())
    _with_extra_js_store(hass)

    asyncio.run(frontend.async_setup_frontend(hass))

    assert hass.data[DATA_EXTRA_MODULE_URL] == {frontend.CARD_URL}


def test_setup_survives_broken_http_layer(tmp_path, monkeypatch):
    """Wirft die HTTP-Schicht, bleibt das Setup ohne Exception (defensiv)."""
    monkeypatch.setattr(frontend, "WWW_DIR", tmp_path)
    hass = FakeHass()
    _with_extra_js_store(hass)

    async def _boom(configs) -> None:
        raise RuntimeError("no http layer")

    hass.http.async_register_static_paths = _boom

    asyncio.run(frontend.async_setup_frontend(hass))

    assert hass.http.registered == []
    assert hass.data[DATA_EXTRA_MODULE_URL] == {frontend.CARD_URL}


def test_unregister_removes_extra_js_fallback(tmp_path, monkeypatch):
    """Rückbau: Fallback-URL wird entfernt, Marker zurückgesetzt, idempotent."""
    monkeypatch.setattr(frontend, "WWW_DIR", tmp_path)
    hass = FakeHass()
    _with_extra_js_store(hass)

    asyncio.run(frontend.async_setup_frontend(hass))
    asyncio.run(frontend.async_unregister_frontend(hass))

    assert hass.data[DATA_EXTRA_MODULE_URL] == set()
    assert frontend.shared_data(hass).get("frontend_card_registered") is None

    # Zweiter Rückbau: kein Fehler (bereits entfernt)
    asyncio.run(frontend.async_unregister_frontend(hass))


def test_unregister_keeps_lovelace_resource(tmp_path, monkeypatch):
    """Lovelace-Ressource bleibt bestehen (Dashboards referenzieren sie)."""
    monkeypatch.setattr(frontend, "WWW_DIR", tmp_path)
    hass = FakeHass()
    resources = FakeResources()
    _with_lovelace(hass, resources)
    _with_extra_js_store(hass)

    asyncio.run(frontend.async_setup_frontend(hass))
    asyncio.run(frontend.async_unregister_frontend(hass))

    assert resources.created  # Ressource unangetastet
    assert frontend.shared_data(hass)["frontend_card_registered"] == "lovelace"
    assert hass.data[DATA_EXTRA_MODULE_URL] == set()

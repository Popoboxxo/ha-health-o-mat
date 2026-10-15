"""Frontend-Anbindung: statische Card-Ressource + automatische Registrierung.

Die Integration liefert ihre eigene Custom-Card als statische Datei
(`www/health-o-mat-card.js`) aus und registriert sie automatisch als
Lovelace-Ressource — die Karte ist damit ohne manuelles YAML nutzbar
(docs/CONCEPT-UI.md, Abschnitte 5.1/5.3).

Alle Schritte sind idempotent (prozessweiter Marker in
`hass.data[DOMAIN]["shared"]`) und defensiv: ein fehlendes `www/`-Verzeichnis,
ein Lovelace-YAML-Modus oder eine abweichende Lovelace-Datenstruktur brechen
das Setup NIE ab, sondern führen höchstens zu einem Fallback
(`frontend.add_extra_js_url`) bzw. zu einem Warn-Log.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN

try:  # Frontend/HTTP sind HA-Kernbestandteile; Import bleibt trotzdem tolerant,
    # damit das Integrationspaket auch ohne diese Komponenten importierbar ist.
    from homeassistant.components.frontend import add_extra_js_url, remove_extra_js_url
    from homeassistant.components.http import StaticPathConfig
except ImportError:  # pragma: no cover - nur ohne HTTP-/Frontend-Komponente
    add_extra_js_url = None  # type: ignore[assignment]
    remove_extra_js_url = None  # type: ignore[assignment]
    StaticPathConfig = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)

# URL-Präfix, unter dem das Verzeichnis `www/` ausgeliefert wird.
URL_BASE = "/health_o_mat"
CARD_FILENAME = "health-o-mat-card.js"
CARD_URL = f"{URL_BASE}/{CARD_FILENAME}"

# Ausgeliefertes Verzeichnis (relativ zum Integrationspaket).
WWW_DIR = Path(__file__).parent / "www"

# Marker im prozessweiten Shared-Bereich (`hass.data[DOMAIN]["shared"]`).
_STATIC_PATH_MARKER = "frontend_static_path"
_CARD_MARKER = "frontend_card_registered"

# Registrierungswege der Card (Wert des `_CARD_MARKER`).
_METHOD_LOVELACE = "lovelace"
_METHOD_EXTRA_JS = "extra_js"


def shared_data(hass: HomeAssistant) -> dict[str, Any]:
    """Prozessweiter Shared-Bereich der Integration (Marker-Ablage)."""
    return hass.data.setdefault(DOMAIN, {}).setdefault("shared", {})


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Registriert statischen Pfad + Card-Ressource genau EINMAL pro HA-Prozess.

    Wird von jedem Config-Entry-Setup aufgerufen; die Marker im Shared-Bereich
    machen wiederholte Aufrufe zu No-ops (keine Doppel-Registrierung).
    """
    shared = shared_data(hass)
    await _async_register_static_path(hass, shared)
    await _async_register_card_resource(hass, shared)


async def async_unregister_frontend(hass: HomeAssistant) -> None:
    """Rückbau beim Entladen des letzten Entries (defensiv, idempotent).

    Entfernt nur den Fallback (`add_extra_js_url`) — und nur, wenn dieser
    tatsächlich benutzt wurde. Der statische Pfad ist in HA nicht abmeldbar;
    eine als Lovelace-Ressource angelegte Card bleibt bewusst stehen, weil
    bestehende Dashboards sie referenzieren (Entfernen würde sie brechen).
    """
    shared = shared_data(hass)
    if shared.get(_CARD_MARKER) != _METHOD_EXTRA_JS:
        return
    if remove_extra_js_url is not None:
        try:
            remove_extra_js_url(hass, CARD_URL)
        except Exception:  # noqa: BLE001 - HA-internes Datenformat, nie unload-kritisch
            _LOGGER.debug("Health-O-Mat: Extra-JS-URL %s war nicht registriert", CARD_URL)
    shared.pop(_CARD_MARKER, None)


async def _async_register_static_path(hass: HomeAssistant, shared: dict[str, Any]) -> None:
    """`www/` unter URL_BASE ausliefern (einmal pro Prozess, selbstheilend)."""
    if shared.get(_STATIC_PATH_MARKER) or StaticPathConfig is None:
        return
    www_dir = WWW_DIR
    if not www_dir.is_dir():
        # Kein Marker setzen: beim nächsten Entry-Setup erneut versuchen, sobald
        # das Verzeichnis (z. B. nach einem Sync ohne HA-Neustart) existiert.
        _LOGGER.warning(
            "Health-O-Mat: %s fehlt — die Custom-Card wird nicht ausgeliefert",
            www_dir,
        )
        return
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(www_dir), cache_headers=True)]
        )
    except Exception:  # noqa: BLE001 - HTTP-Schicht variiert je HA-Version
        _LOGGER.exception(
            "Health-O-Mat: statischer Pfad %s konnte nicht registriert werden", URL_BASE
        )
        return
    shared[_STATIC_PATH_MARKER] = True


async def _async_register_card_resource(hass: HomeAssistant, shared: dict[str, Any]) -> None:
    """Card als Lovelace-Ressource anlegen, sonst `add_extra_js_url` als Fallback."""
    if shared.get(_CARD_MARKER):
        return
    if await _async_register_lovelace_resource(hass):
        shared[_CARD_MARKER] = _METHOD_LOVELACE
        return
    if _add_extra_js_url(hass):
        shared[_CARD_MARKER] = _METHOD_EXTRA_JS


async def _async_register_lovelace_resource(hass: HomeAssistant) -> bool:
    """Card in die Lovelace-Ressourcen eintragen. True = registriert/vorhanden.

    Nur im Storage-Modus möglich (YAML-Modus ist nicht schreibbar) — deshalb
    Duck-Typing auf `async_create_item` statt eines harten Imports interner
    Klassen: eine anders strukturierte Lovelace-Datenhaltung führt so zu
    `False` (und damit zum Fallback) statt zu einem Import-/Attributfehler.
    """
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA
    except ImportError:  # pragma: no cover - Lovelace ist HA-Kernbestandteil
        return False

    resources = getattr(hass.data.get(LOVELACE_DATA), "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return False
    try:
        if not getattr(resources, "loaded", True):
            await resources.async_load()
            resources.loaded = True
        items = resources.async_items() or []
        if any(_is_card_resource(item) for item in items):
            return True  # Dedupe: bereits vorhanden (auch durch HACS-Plugin)
        await resources.async_create_item({"res_type": "module", "url": CARD_URL})
    except Exception:  # noqa: BLE001 - Lovelace/Dashboard-Storage ist optional
        _LOGGER.exception("Health-O-Mat: Lovelace-Ressource %s nicht anlegbar", CARD_URL)
        return False
    return True


def _is_card_resource(item: Any) -> bool:
    """True, wenn ein Lovelace-Ressourcen-Eintrag unsere Card (ohne Cache-Buster) ist."""
    if not isinstance(item, dict):
        return False
    url = item.get("url")
    if not isinstance(url, str):
        return False
    return url.split("?", 1)[0].rstrip("/") == CARD_URL


def _add_extra_js_url(hass: HomeAssistant) -> bool:
    """Fallback: Card als Extra-JS-Modul laden (nur wenn Frontend geladen ist)."""
    if add_extra_js_url is None:
        return False
    try:
        add_extra_js_url(hass, CARD_URL)
    except Exception:  # noqa: BLE001 - Frontend nicht (oder anders) initialisiert
        _LOGGER.warning(
            "Health-O-Mat: Custom-Card %s konnte nicht als Extra-JS registriert werden", CARD_URL
        )
        return False
    return True

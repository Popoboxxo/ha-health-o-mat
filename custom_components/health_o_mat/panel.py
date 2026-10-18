"""Sidebar-Panel „Health-O-Mat" (L2) — opt-in, idempotent, unload-sicher.

Das Panel wird über `panel_custom.async_register_panel` registriert und lädt
dieselbe Frontend-Ebene wie die L1-Card (`www/`, ausgeliefert unter `URL_BASE`
durch `frontend.py`) — nur als eigene JS-Datei (`health-o-mat-panel.js`).

Eigenschaften (docs/CONCEPT-UI.md §5.1/§8.3):

- **Opt-in:** Registrierung nur, wenn mindestens ein Config-Entry die Option
  `enable_sidebar_panel` gesetzt hat (Default AUS — „weniger Überraschung").
- **Genau EIN Panel pro Prozess:** Mehrere Config-Entries (= Personen) teilen
  sich EIN Sidebar-Panel; ein Marker im prozessweiten Shared-Bereich macht
  wiederholte Aufrufe zu No-ops.
- **Setup-/Unload-sicher:** Registrierung/Entfernung sind defensiv — ein
  fehlendes `panel_custom` oder eine abweichende HA-Signatur führen zu einem
  Warn-Log, nie zu einem Setup-Abbruch.

Die Options-/Entscheidungslogik (`panel_enabled`, `panel_requested`) ist
HA-frei und ohne Home-Assistant-Runtime testbar.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from homeassistant.core import HomeAssistant

from .frontend import shared_data, versioned_url

try:  # panel_custom ist HA-Kernbestandteil; Import bleibt trotzdem tolerant,
    # damit das Integrationspaket auch ohne diese Komponente importierbar ist.
    from homeassistant.components import panel_custom
except ImportError:  # pragma: no cover - nur ohne Panel-Komponente
    panel_custom = None  # type: ignore[assignment]

try:  # Entfernen läuft über die Frontend-Komponente (Panel-Registry dort).
    from homeassistant.components.frontend import async_remove_panel
except ImportError:  # pragma: no cover - nur ohne Frontend-Komponente
    async_remove_panel = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)

# Panel-Identität (stabil halten: der Webcomponent-Name ist im JS verankert).
PANEL_URL_PATH = "health-o-mat"
WEBCOMPONENT_NAME = "health-o-mat-panel"
PANEL_JS_FILENAME = "health-o-mat-panel.js"
PANEL_MODULE_URL = versioned_url(PANEL_JS_FILENAME)
SIDEBAR_TITLE = "Health-O-Mat"
SIDEBAR_ICON = "mdi:heart-pulse"

# Options-Schlüssel für das Opt-in (config_flow + __init__ teilen ihn).
OPTION_ENABLE_SIDEBAR_PANEL = "enable_sidebar_panel"

# Marker im prozessweiten Shared-Bereich (`hass.data[DOMAIN]["shared"]`).
_PANEL_MARKER = "panel_registered"


def panel_enabled(options: Mapping[str, Any] | None) -> bool:
    """Opt-in-Auswertung: True nur bei ausdrücklich gesetzter Option (Default AUS)."""
    if not isinstance(options, Mapping):
        return False
    return bool(options.get(OPTION_ENABLE_SIDEBAR_PANEL, False))


def panel_requested(entries: Iterable[Any]) -> bool:
    """True, sobald EIN Config-Entry das Panel aktiviert (Domain-weit, EIN Panel)."""
    return any(panel_enabled(getattr(entry, "options", None)) for entry in entries)


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Registriert das Sidebar-Panel genau EINMAL pro HA-Prozess (idempotent).

    Wird von jedem Entry-Setup (bei aktiver Option) und bei Options-Änderungen
    aufgerufen; der Marker im Shared-Bereich macht wiederholte Aufrufe zu No-ops.
    """
    if panel_custom is None:  # pragma: no cover - nur ohne Panel-Komponente
        _LOGGER.warning("Health-O-Mat: panel_custom fehlt — Sidebar-Panel nicht registrierbar")
        return
    shared = shared_data(hass)
    if shared.get(_PANEL_MARKER):
        return
    try:
        # Signatur der installierten HA-Version (2026.2.3):
        # async_register_panel(hass, frontend_url_path, webcomponent_name,
        #     sidebar_title, sidebar_icon, js_url, module_url, embed_iframe,
        #     trust_external, config, require_admin, config_panel_domain)
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=WEBCOMPONENT_NAME,
            sidebar_title=SIDEBAR_TITLE,
            sidebar_icon=SIDEBAR_ICON,
            module_url=PANEL_MODULE_URL,
            require_admin=False,
            config={},
        )
    except Exception:  # noqa: BLE001 - UI-Zusatz darf das Setup nie kippen
        _LOGGER.exception("Health-O-Mat: Sidebar-Panel nicht registrierbar")
        return
    shared[_PANEL_MARKER] = True


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Entfernt das Sidebar-Panel (defensiv, versions-tolerant, idempotent).

    Ohne gesetzten Marker passiert nichts. `frontend.async_remove_panel` ist
    synchron und mit `warn_if_unknown=False` aufgerufen, damit ein bereits
    entferntes Register keinen Warn-Spam erzeugt.
    """
    shared = shared_data(hass)
    if not shared.get(_PANEL_MARKER):
        return
    if async_remove_panel is not None:
        try:
            async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
        except Exception:  # noqa: BLE001 - Rückbau ist nie unload-kritisch
            _LOGGER.debug("Health-O-Mat: Panel %s war nicht registriert", PANEL_URL_PATH)
    shared.pop(_PANEL_MARKER, None)


async def async_apply_panel_state(hass: HomeAssistant, entries: Iterable[Any]) -> bool:
    """Wendet den gewünschten Panel-Zustand domain-weit an (idempotent).

    Registriert, sobald mindestens ein Entry die Option gesetzt hat; entfernt
    das Panel andernfalls. Mehrfache Aufrufe (mehrere Entries, wiederholte
    Options-Änderungen) erzeugen keine Doppel-Registrierung.
    """
    if panel_requested(entries):
        await async_setup_panel(hass)
        return True
    await async_unregister_panel(hass)
    return False

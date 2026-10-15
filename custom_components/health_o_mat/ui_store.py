"""Per-User-UI-Einstellungen (HA-`Store`, keyed `user_id`) — L2-Panel-Support.

Merkt sich je HA-Nutzer, welche Person im Panel ausgewählt ist (stabil über die
`entry_id`, nicht über den Anzeigenamen) plus ein kleines, freies `prefs`-Dict
für reine Darstellungswünsche (docs/CONCEPT-UI.md §5.4).

**Datenschutz:** Hier landen bewusst NUR UI-Zustände — keine personenbezogenen
Gesundheitsdaten. Eine Whitelist (`UI_SETTING_KEYS`) erzwingt das: unbekannte
Schlüssel werden beim Merge verworfen, statt versehentlich persistiert zu werden.

Die Merge-/Default-Logik (`default_ui_settings`, `merge_ui_settings`) ist
HA-frei und damit ohne Home-Assistant-Runtime testbar.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

# Eigener Store-Namespace (getrennt vom Haupt-/Archiv-Store der Personen).
UI_STORE_KEY = "health_o_mat.ui"
UI_STORE_VERSION = 1

SELECTED_PERSON_KEY = "selected_person"
PREFS_KEY = "prefs"

# Whitelist: nur diese Schlüssel werden je Nutzer persistiert. Schützt zugleich
# davor, versehentlich Gesundheitsdaten in den UI-Store zu schreiben.
UI_SETTING_KEYS = (SELECTED_PERSON_KEY, PREFS_KEY)


def default_ui_settings() -> dict[str, Any]:
    """Frische Default-Struktur je Nutzer (keine geteilten Referenzen)."""
    return {SELECTED_PERSON_KEY: None, PREFS_KEY: {}}


def merge_ui_settings(
    current: Mapping[str, Any] | None,
    updates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reine Merge-Logik: Defaults ← bekannte Alt-Werte ← Updates (whitelisted).

    - `selected_person`: nur `str` oder `None` (leer → None).
    - `prefs`: flach gemergt (bestehende Schlüssel bleiben, sofern nicht
      überschrieben).
    - Unbekannte Schlüssel (weder `selected_person` noch `prefs`) werden
      verworfen.
    """
    merged = default_ui_settings()

    if isinstance(current, Mapping):
        selected = current.get(SELECTED_PERSON_KEY)
        merged[SELECTED_PERSON_KEY] = selected if isinstance(selected, str) else None
        prefs = current.get(PREFS_KEY)
        if isinstance(prefs, Mapping):
            merged[PREFS_KEY] = dict(prefs)

    if not isinstance(updates, Mapping):
        return merged

    if SELECTED_PERSON_KEY in updates:
        selected = updates[SELECTED_PERSON_KEY]
        merged[SELECTED_PERSON_KEY] = selected if isinstance(selected, str) else None
    if PREFS_KEY in updates:
        prefs = updates[PREFS_KEY]
        if isinstance(prefs, Mapping):
            merged[PREFS_KEY] = {**merged[PREFS_KEY], **dict(prefs)}

    return merged


class HealthOMatUiStore:
    """Pro-HA-Nutzer-UI-Einstellungen, persistiert via HA-Store."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store = Store(hass, UI_STORE_VERSION, UI_STORE_KEY)
        self._users: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        """Laden + normalisieren (kaputte/fehlende Daten → leerer Start)."""
        data = await self._store.async_load()
        users = data.get("users") if isinstance(data, dict) else None
        if not isinstance(users, Mapping):
            self._users = {}
            return
        self._users = {
            str(user_id): merge_ui_settings(settings)
            for user_id, settings in users.items()
            if isinstance(settings, Mapping)
        }

    def get(self, user_id: str | None) -> dict[str, Any]:
        """Einstellungen eines Nutzers — immer eine frische Kopie (nie None)."""
        if user_id is None:
            return default_ui_settings()
        current = self._users.get(str(user_id))
        return merge_ui_settings(current)

    async def async_set(self, user_id: str, **updates: Any) -> dict[str, Any]:
        """Whitelisted Updates mergen, persistieren und das Ergebnis liefern.

        Beispiel: ``await store.async_set("user-1", selected_person="entry-1")``
        oder ``await store.async_set("user-1", prefs={"compact": True})``.
        """
        uid = str(user_id)
        merged = merge_ui_settings(self._users.get(uid), updates)
        self._users[uid] = merged
        await self._async_save()
        return merge_ui_settings(merged)

    def all_users(self) -> dict[str, dict[str, Any]]:
        """Alle Nutzer-Einstellungen (Kopien, für Tests/Diagnostics)."""
        return {user_id: merge_ui_settings(settings) for user_id, settings in self._users.items()}

    async def _async_save(self) -> None:
        await self._store.async_save({"users": self._users})

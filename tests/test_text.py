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


# --- REQ-HOM-009: pro-Person Bereichs-Toggles filtern das Text-Setup ---

_ENTRY_ID = "test-entry-1"
_FREETEXT_ID = "test-entry-1_text_freetext"


def _text_setup(options: dict) -> set[str]:
    added: list = []

    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = _ENTRY_ID
    entry.options = options
    coord = MagicMock()
    store = MagicMock()
    hass.data = {
        "health_o_mat": {
            _ENTRY_ID: {"coordinator": coord},
            "shared": {"store": store},
        }
    }

    _run(text_module.async_setup_entry(hass, entry, lambda ents: added.extend(ents)))
    return {e._attr_unique_id for e in added}


def test_text_setup_old_entry_without_options_has_drink_area():
    """[REQ-HOM-009] Alt-Entry ohne areas-Option = Getränke + BP aktiv."""
    assert _text_setup({}) == {_FREETEXT_ID, _NOTE_ID}


def test_text_setup_drink_disabled_creates_no_freetext_entity():
    """[REQ-HOM-009] drink AUS → kein Freitext-Entity (BP bleibt aktiv)."""
    assert _text_setup({"areas": {"drink": False}}) == {_NOTE_ID}


def test_text_setup_only_drink_when_bp_and_wellbeing_disabled():
    """[REQ-HOM-009] bp + wellbeing AUS ändert nichts (Text ist Drink-only)."""
    assert _text_setup({"areas": {"bp": False, "wellbeing": False}}) == {_FREETEXT_ID}


def test_text_unique_ids_stable_across_area_toggle():
    """[REQ-HOM-009] De-/Reaktivieren erzeugt dieselbe unique_id."""
    on_ids = _text_setup({})
    off_ids = _text_setup({"areas": {"drink": False}})
    on_again_ids = _text_setup({"areas": {"drink": True}})

    assert on_ids == {_FREETEXT_ID, _NOTE_ID}
    assert off_ids == {_NOTE_ID}
    assert on_again_ids == on_ids


# --- REQ-HOM-010: Mess-Notiz-Entity (Blutdruck-Bereich) ---

_NOTE_ID = "test-entry-1_text_measurement_note"


def _note_entity(options: dict | None = None):
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.options = options or {}
    store = MagicMock()
    store.pending_note.return_value = ""
    store.set_pending_note = AsyncMock()
    entity = text_module.MeasurementNoteEntity(MagicMock(), entry, store)
    entity.hass = MagicMock()
    # Fake Entity has no async_write_ha_state; stub it so the entity can push
    # its own state (should_poll is False) and tests can assert on the push.
    entity.async_write_ha_state = MagicMock()
    return entity, store


def test_measurement_note_entity_created_when_bp_active():
    """[REQ-HOM-010] BP aktiv → Freitext + Mess-Notiz."""
    assert _text_setup({}) == {_FREETEXT_ID, _NOTE_ID}


def test_measurement_note_entity_absent_when_bp_disabled():
    """[REQ-HOM-010] bp AUS → nur Freitext-Entity."""
    assert _text_setup({"areas": {"bp": False}}) == {_FREETEXT_ID}


def test_measurement_note_unique_id_is_stable():
    """[REQ-HOM-010] De-/Reaktivieren von bp erzeugt dieselbe unique_id."""
    on_ids = _text_setup({})
    off_ids = _text_setup({"areas": {"bp": False}})
    on_again_ids = _text_setup({"areas": {"bp": True}})

    assert _NOTE_ID in on_ids
    assert _NOTE_ID not in off_ids
    assert on_again_ids == on_ids


def test_measurement_note_native_value_reads_store():
    """[REQ-HOM-010] Der Wert kommt aus dem persistierten Eingabe-Dict."""
    entity, store = _note_entity()
    store.pending_note.return_value = "morgens"

    assert entity.native_value == "morgens"
    store.pending_note.assert_called_once_with("e1")


def test_measurement_note_async_set_value_writes_store():
    """[REQ-HOM-010] Setzen schreibt in den Store (persistiert, neustartfest)."""
    entity, store = _note_entity()

    _run(entity.async_set_value("abends"))

    store.set_pending_note.assert_awaited_once_with("e1", "abends")


def test_measurement_note_async_set_value_writes_state_immediately():
    """[REQ-HOM-010] Setzen macht den neuen Wert sofort zum Entity-State.

    Regression (E2E): der Store hielt die Notiz, die Entity blieb auf "" —
    CoordinatorEntity.should_poll ist False, HA pusht den State also nicht
    selbst; ohne async_write_ha_state() fehlt das unmittelbare Feedback.
    """
    entity, store = _note_entity()
    pending = {"value": ""}
    store.pending_note.side_effect = lambda _entry_id: pending["value"]

    async def _set(_entry_id: str, value: str | None) -> None:
        pending["value"] = value or ""

    store.set_pending_note.side_effect = _set

    _run(entity.async_set_value("abends"))

    assert entity.native_value == "abends"
    entity.async_write_ha_state.assert_called_once_with()


def test_measurement_note_has_translation_key_and_no_name_literal():
    """[REQ-HOM-010] Kein Namens-Literal; Anzeigename kommt aus translations."""
    entity, _ = _note_entity()
    cls = text_module.MeasurementNoteEntity

    assert entity.translation_key == "measurement_note"
    assert entity.has_entity_name is True
    assert "_attr_name" not in cls.__dict__
    assert "name" not in cls.__dict__

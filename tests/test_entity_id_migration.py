"""Tests: HA-free entity id migration logic (REQ-HOM-130, Spec §6.1).

`migration.py` is loaded by file path on purpose (no `custom_components`
import, no fake HA package): the module must import neither `homeassistant`
nor the surrounding package. A relative import would fail right here with
`ImportError: attempted relative import with no known parent package`.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "health_o_mat")
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "_hom_migration", os.path.join(_COMPONENT_DIR, "migration.py")
    )
    module = importlib.util.module_from_spec(spec)
    # Register before exec: ``dataclasses`` resolves string annotations via
    # ``sys.modules[cls.__module__]`` (``from __future__ import annotations``),
    # so an unregistered module would raise AttributeError on the first
    # ``@dataclass``. The module is still loaded by file path only.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load_migration()

ENTRY = "01JABCDEF"
CATALOG = ("alt", "crp", "creatinine", "h_moglobin")


def test_req_hom_130_quick_drink_target_is_one_based():
    assert migration.quick_drink_target("health_o_mat_max", 0) == ("health_o_mat_max_quick_drink_1")
    assert migration.quick_drink_target("health_o_mat_max", 3) == ("health_o_mat_max_quick_drink_4")


@pytest.mark.parametrize(
    ("unique_id", "expected"),
    [
        (f"{ENTRY}_button_quick_0", 0),
        (f"{ENTRY}_button_quick_10", 10),
        ("other_entry_button_quick_0", None),
        (f"{ENTRY}_button_quick_", None),
        (f"{ENTRY}_button_quick_01", None),
        (f"{ENTRY}_button_quick_x", None),
        (f"{ENTRY}_button_quick_-1", None),
        (f"{ENTRY}_button_quick_0_extra", None),
        (f"{ENTRY}_button_book_custom", None),
    ],
)
def test_req_hom_130_parse_quick_drink_index(unique_id, expected):
    assert migration.parse_quick_drink_index(unique_id, ENTRY) == expected


def test_req_hom_130_custom_lab_target_uses_key():
    assert migration.custom_lab_target("health_o_mat_max", "vitamin_d") == (
        "health_o_mat_max_lab_vitamin_d"
    )
    assert migration.custom_lab_target("health_o_mat_max", "h_moglobin") == (
        "health_o_mat_max_lab_h_moglobin"
    )


def test_req_hom_130_parse_custom_lab_key_skips_catalog():
    assert migration.parse_custom_lab_key(f"{ENTRY}_lab_crp", ENTRY, CATALOG) is None
    assert migration.parse_custom_lab_key(f"{ENTRY}_lab_vitamin_d", ENTRY, CATALOG) == ("vitamin_d")
    assert migration.parse_custom_lab_key("other_entry_lab_vitamin_d", ENTRY, CATALOG) is None
    assert migration.parse_custom_lab_key(f"{ENTRY}_lab_", ENTRY, CATALOG) is None
    assert (
        migration.parse_custom_lab_key(f"{ENTRY}_binary_lab_warning_liver", ENTRY, CATALOG) is None
    )


def test_req_hom_130_is_safe_key_accepts_slugs_only():
    assert migration.is_safe_key("vitamin_d")
    assert migration.is_safe_key("h_moglobin")
    assert migration.is_safe_key("d3")
    for unsafe in ("Vitamin D", "vitamin-d", "vitamin__d", "_vitamin", "vitamin_", ""):
        assert not migration.is_safe_key(unsafe), unsafe


# --- resolve_device_slug (Spec §2.3 / §6.1) --------------------------------


def _candidate(entity_id: str, device_id: str | None = "dev1") -> dict:
    return {"entity_id": entity_id, "device_id": device_id}


def _anchor(entity_id: str, translation_key: str | None, device_id: str | None = "dev1") -> dict:
    return {
        "entity_id": entity_id,
        "translation_key": translation_key,
        "device_id": device_id,
    }


def test_req_hom_130_resolve_accepts_hint_with_matching_anchors():
    resolution = migration.resolve_device_slug(
        [_candidate("button.health_o_mat_max_quick_drink_1")],
        [
            _anchor("sensor.health_o_mat_max_drinks_today", "today"),
            _anchor("sensor.health_o_mat_max_daily_goal_progress", "goal_percent"),
        ],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution("health_o_mat_max", None)


def test_req_hom_130_resolve_falls_back_to_translation_anchors():
    resolution = migration.resolve_device_slug(
        [_candidate("button.health_o_mat_dana_quick_drink_1")],
        [
            _anchor("sensor.health_o_mat_dana_drinks_today", "today"),
            _anchor("sensor.health_o_mat_dana_daily_goal_progress", "goal_percent"),
        ],
        hint=None,
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution("health_o_mat_dana", None)


def test_req_hom_130_resolve_ignores_user_labels():
    """B-2 counter-example: four drink labels must never yield `..._glas`."""
    resolution = migration.resolve_device_slug(
        [
            _candidate("button.health_o_mat_max_glas_wasser"),
            _candidate("button.health_o_mat_max_glas_saft"),
            _candidate("button.health_o_mat_max_glas_tee"),
            _candidate("button.health_o_mat_max_glas_kaffee"),
        ],
        [],
        hint=None,
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(None, migration.SKIP_DEVICE_SLUG_UNRESOLVED)


def test_req_hom_130_resolve_hint_conflict_is_ambiguous():
    resolution = migration.resolve_device_slug(
        [_candidate("button.health_o_mat_alt_quick_drink_1")],
        [
            _anchor("sensor.health_o_mat_alt_drinks_today", "today"),
            _anchor("sensor.health_o_mat_alt_daily_goal_progress", "goal_percent"),
        ],
        hint="health_o_mat_neu",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(None, migration.SKIP_DEVICE_SLUG_AMBIGUOUS)


def test_req_hom_130_resolve_area_prefix_matches_hint():
    """The area segment stays part of the ids (P.endswith("_" + hint))."""
    resolution = migration.resolve_device_slug(
        [_candidate("button.wohnzimmer_health_o_mat_max_quick_drink_1")],
        [
            _anchor("sensor.wohnzimmer_health_o_mat_max_drinks_today", "today"),
            _anchor("sensor.wohnzimmer_health_o_mat_max_daily_goal_progress", "goal_percent"),
        ],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution("wohnzimmer_health_o_mat_max", None)


def test_req_hom_130_resolve_lab_only_with_hint_uses_hint():
    resolution = migration.resolve_device_slug(
        [_candidate("sensor.health_o_mat_max_vitamin_d")],
        [
            _anchor("sensor.health_o_mat_max_lab_crp", "lab_crp"),
            _anchor("sensor.health_o_mat_max_lab_creatinine", "lab_creatinine"),
        ],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution("health_o_mat_max", None)


def test_req_hom_130_resolve_lab_only_without_hint_is_unresolved():
    resolution = migration.resolve_device_slug(
        [_candidate("sensor.health_o_mat_max_vitamin_d")],
        [
            _anchor("sensor.health_o_mat_max_lab_crp", "lab_crp"),
            _anchor("sensor.health_o_mat_max_lab_creatinine", "lab_creatinine"),
        ],
        hint=None,
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(None, migration.SKIP_DEVICE_SLUG_UNRESOLVED)


def test_req_hom_130_resolve_single_anchor_is_unresolved():
    resolution = migration.resolve_device_slug(
        [_candidate("button.health_o_mat_max_quick_drink_1")],
        [_anchor("sensor.health_o_mat_max_drinks_today", "today")],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(None, migration.SKIP_DEVICE_SLUG_UNRESOLVED)


def test_req_hom_130_resolve_rejects_candidate_outside_prefix():
    resolution = migration.resolve_device_slug(
        [
            _candidate("button.health_o_mat_max_quick_drink_1"),
            _candidate("button.garden_light_quick_drink_2"),
        ],
        [
            _anchor("sensor.health_o_mat_max_drinks_today", "today"),
            _anchor("sensor.health_o_mat_max_daily_goal_progress", "goal_percent"),
        ],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(None, migration.SKIP_DEVICE_SLUG_AMBIGUOUS)


def test_req_hom_130_resolve_rejects_foreign_device():
    """Acceptance demands: every candidate belongs to the anchor device."""
    resolution = migration.resolve_device_slug(
        [
            _candidate("button.health_o_mat_max_quick_drink_1"),
            _candidate("button.health_o_mat_max_quick_drink_2", device_id="dev2"),
        ],
        [
            _anchor("sensor.health_o_mat_max_drinks_today", "today"),
            _anchor("sensor.health_o_mat_max_daily_goal_progress", "goal_percent"),
        ],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(None, migration.SKIP_DEVICE_SLUG_AMBIGUOUS)


def test_req_hom_130_resolve_without_candidates_is_unresolved():
    resolution = migration.resolve_device_slug(
        [],
        [
            _anchor("sensor.health_o_mat_max_drinks_today", "today"),
            _anchor("sensor.health_o_mat_max_daily_goal_progress", "goal_percent"),
        ],
        hint="health_o_mat_max",
        device_id="dev1",
    )
    assert resolution == migration.DeviceSlugResolution(None, migration.SKIP_DEVICE_SLUG_UNRESOLVED)


# --- build_migration_plan (Spec §3.1 / §6.1) -------------------------------

_SLUG = "health_o_mat_max"


def _entity(
    entity_id: str,
    unique_id: str,
    *,
    translation_key: str | None = None,
    device_id: str | None = "dev1",
) -> dict:
    return {
        "entity_id": entity_id,
        "unique_id": unique_id,
        "translation_key": translation_key,
        "device_id": device_id,
    }


def _mixed_entities() -> list[dict]:
    return [
        _entity(f"button.{_SLUG}_glas_wasser", f"{ENTRY}_button_quick_0"),
        _entity(f"button.{_SLUG}_tasse_kaffee", f"{ENTRY}_button_quick_2"),
        _entity(f"sensor.{_SLUG}_vitamin_d", f"{ENTRY}_lab_vitamin_d"),
        _entity(f"sensor.{_SLUG}_crp", f"{ENTRY}_lab_crp", translation_key="lab_crp"),
        _entity(f"sensor.{_SLUG}_drinks_today", f"{ENTRY}_today", translation_key="today"),
        _entity(
            f"sensor.{_SLUG}_daily_goal_progress",
            f"{ENTRY}_goal_percent",
            translation_key="goal_percent",
        ),
        _entity(
            f"button.{_SLUG}_book_custom_amount",
            f"{ENTRY}_button_book_custom",
            translation_key="book_custom",
        ),
    ]


def _plan(entities, *, hint=_SLUG, occupied=()):
    return migration.build_migration_plan(
        ENTRY,
        entities,
        device_slug_hint=hint,
        device_id="dev1",
        catalog_keys=CATALOG,
        occupied_entity_ids=occupied,
    )


def test_req_hom_130_plan_renames_only_f1_f2():
    plan = _plan(_mixed_entities())
    assert plan.device_slug == _SLUG
    assert plan.skipped == ()
    assert {(item.source_entity_id, item.target_entity_id) for item in plan.renames} == {
        (f"button.{_SLUG}_glas_wasser", f"button.{_SLUG}_quick_drink_1"),
        (f"button.{_SLUG}_tasse_kaffee", f"button.{_SLUG}_quick_drink_3"),
        (f"sensor.{_SLUG}_vitamin_d", f"sensor.{_SLUG}_lab_vitamin_d"),
    }


def test_req_hom_130_plan_is_noop_at_target():
    plan = _plan(
        [
            _entity(f"button.{_SLUG}_quick_drink_1", f"{ENTRY}_button_quick_0"),
            _entity(f"sensor.{_SLUG}_lab_vitamin_d", f"{ENTRY}_lab_vitamin_d"),
            _entity(f"sensor.{_SLUG}_drinks_today", f"{ENTRY}_today", translation_key="today"),
            _entity(
                f"sensor.{_SLUG}_daily_goal_progress",
                f"{ENTRY}_goal_percent",
                translation_key="goal_percent",
            ),
        ],
        occupied=(f"button.{_SLUG}_quick_drink_1", f"sensor.{_SLUG}_lab_vitamin_d"),
    )
    assert plan.renames == ()
    assert plan.skipped == ()


def test_req_hom_130_plan_skips_occupied_target():
    plan = _plan(_mixed_entities(), occupied=(f"button.{_SLUG}_quick_drink_1",))
    assert [item.reason for item in plan.skipped] == [migration.SKIP_TARGET_OCCUPIED]
    assert plan.skipped[0].source_entity_id == f"button.{_SLUG}_glas_wasser"
    assert plan.skipped[0].target_entity_id == f"button.{_SLUG}_quick_drink_1"
    # The rest of the plan is unaffected — a collision never blocks other renames.
    assert len(plan.renames) == 2


def test_req_hom_130_plan_skips_invalid_custom_key():
    plan = _plan(
        [
            _entity(f"sensor.{_SLUG}_vitamin d", f"{ENTRY}_lab_vitamin d"),
            _entity(f"sensor.{_SLUG}_drinks_today", f"{ENTRY}_today", translation_key="today"),
            _entity(
                f"sensor.{_SLUG}_daily_goal_progress",
                f"{ENTRY}_goal_percent",
                translation_key="goal_percent",
            ),
        ]
    )
    assert [item.reason for item in plan.skipped] == [migration.SKIP_INVALID_KEY]
    assert plan.skipped[0].target_entity_id is None


def _lab_only_entities() -> list[dict]:
    """Only lab anchors: the suffix token (`lab`) does not diverge (Spec §2.3)."""
    return [
        _entity(f"sensor.{_SLUG}_vitamin_d", f"{ENTRY}_lab_vitamin_d"),
        _entity(f"sensor.{_SLUG}_lab_crp", f"{ENTRY}_lab_crp", translation_key="lab_crp"),
        _entity(
            f"sensor.{_SLUG}_lab_creatinine",
            f"{ENTRY}_lab_creatinine",
            translation_key="lab_creatinine",
        ),
    ]


def test_req_hom_130_plan_propagates_device_slug_reasons():
    # No hint + non-diverging anchors -> unresolved (never a guessed `..._lab`).
    unresolved = _plan(_lab_only_entities(), hint=None)
    assert {item.reason for item in unresolved.skipped} == {migration.SKIP_DEVICE_SLUG_UNRESOLVED}
    assert unresolved.device_slug is None
    assert unresolved.renames == ()

    # Hint present but in no boundary relation to the anchor prefix -> ambiguous.
    ambiguous = _plan(_lab_only_entities(), hint="health_o_mat_neu")
    assert {item.reason for item in ambiguous.skipped} == {migration.SKIP_DEVICE_SLUG_AMBIGUOUS}
    assert ambiguous.renames == ()


def test_req_hom_130_plan_deterministic_order():
    first = _plan(_mixed_entities())
    second = _plan(_mixed_entities())
    assert first == second
    assert [item.source_entity_id for item in first.renames] == [
        f"button.{_SLUG}_glas_wasser",
        f"button.{_SLUG}_tasse_kaffee",
        f"sensor.{_SLUG}_vitamin_d",
    ]


def test_req_hom_130_plan_ignores_catalog_and_translation_entities():
    plan = _plan(_mixed_entities())
    touched = {item.source_entity_id for item in plan.renames} | {
        item.source_entity_id for item in plan.skipped
    }
    assert f"sensor.{_SLUG}_crp" not in touched
    assert f"sensor.{_SLUG}_drinks_today" not in touched
    assert f"button.{_SLUG}_book_custom_amount" not in touched


def test_req_hom_130_plan_is_idempotent_for_a_second_pass():
    """After applying the first plan, a second pass over the new ids is empty."""
    first = _plan(_mixed_entities())
    renamed = {item.source_entity_id: item.target_entity_id for item in first.renames}
    second_entities = [
        {**entity, "entity_id": renamed.get(entity["entity_id"], entity["entity_id"])}
        for entity in _mixed_entities()
    ]
    second = _plan(second_entities)
    assert second.renames == ()
    assert second.skipped == ()

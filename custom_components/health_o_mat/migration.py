"""HA-free migration logic for the entity id switch (REQ-HOM-130).

Nothing in here imports ``homeassistant`` or the surrounding package: every
function is a pure function over registry data that the caller
(``__init__._async_migrate_entity_ids``) passes in as plain mappings. That keeps
the whole plan unit-testable without a Home Assistant installation (Spec §3.1).

Contract (Spec §3.1): target object ids are derived from the ``unique_id`` only —
never from a display-name slug, never from the system language.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

SKIP_DEVICE_SLUG_UNRESOLVED = "device_slug_unresolved"
SKIP_DEVICE_SLUG_AMBIGUOUS = "device_slug_ambiguous"
SKIP_TARGET_OCCUPIED = "target_occupied"
SKIP_INVALID_KEY = "invalid_key"

# ``{entry_id}_button_quick_<index>`` — index is 0-based and canonical: no
# leading zeros, no sign, no trailing noise (Spec §2.1).
_QUICK_DRINK_UNIQUE_ID_INFIX = "_button_quick_"
# ``{entry_id}_lab_<key>`` — the key is the whole remainder (it may contain
# characters that are not slug-safe; the plan rejects those explicitly).
_LAB_UNIQUE_ID_INFIX = "_lab_"
_QUICK_INDEX_RE = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_SAFE_KEY_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")
_SAFE_SLUG_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")


@dataclass(frozen=True)
class DeviceSlugResolution:
    """Resolved object-id prefix of the person device, or a skip reason."""

    slug: str | None
    reason: str | None


@dataclass(frozen=True)
class MigrationRename:
    """One entity id rename; ``unique_id`` is carried for logging/tests only."""

    unique_id: str
    source_entity_id: str
    target_entity_id: str


@dataclass(frozen=True)
class MigrationSkip:
    """One entity that stays as it is; ``reason`` is a ``SKIP_*`` constant."""

    unique_id: str
    source_entity_id: str
    target_entity_id: str | None
    reason: str


@dataclass(frozen=True)
class MigrationPlan:
    """Deterministic, side-effect-free result of one planning pass."""

    device_slug: str | None
    renames: tuple[MigrationRename, ...]
    skipped: tuple[MigrationSkip, ...]


def quick_drink_target(device_slug: str, index: int) -> str:
    """Object-id stem (without domain) of quick-drink slot ``index`` (0-based)."""
    return f"{device_slug}_quick_drink_{index + 1}"


def custom_lab_target(device_slug: str, key: str) -> str:
    """Object-id stem (without domain) of a custom lab marker."""
    return f"{device_slug}_lab_{key}"


def is_safe_key(key: str) -> bool:
    """True when ``key`` can be used verbatim as an object-id suffix."""
    return bool(_SAFE_KEY_RE.fullmatch(key))


def parse_quick_drink_index(unique_id: str, entry_id: str) -> int | None:
    """Index of ``{entry_id}_button_quick_<n>``, else ``None``."""
    prefix = f"{entry_id}{_QUICK_DRINK_UNIQUE_ID_INFIX}"
    if not unique_id.startswith(prefix):
        return None
    suffix = unique_id[len(prefix) :]
    if not _QUICK_INDEX_RE.fullmatch(suffix):
        return None
    return int(suffix)


def parse_custom_lab_key(
    unique_id: str, entry_id: str, catalog_keys: Collection[str]
) -> str | None:
    """Key of ``{entry_id}_lab_<key>`` when it is NOT a catalog marker, else ``None``."""
    prefix = f"{entry_id}{_LAB_UNIQUE_ID_INFIX}"
    if not unique_id.startswith(prefix):
        return None
    key = unique_id[len(prefix) :]
    if not key or key in catalog_keys:
        return None
    return key


def _object_part(entity_id: str) -> str:
    """``button.health_o_mat_max_quick_drink_1`` -> ``health_o_mat_max_quick_drink_1``."""
    _domain, _, object_part = entity_id.partition(".")
    return object_part


def _tokens(object_part: str) -> list[str]:
    return [token for token in object_part.split("_") if token]


def _common_prefix_sequence(sequences: Sequence[Sequence[str]]) -> list[str]:
    """Longest common leading token sequence (``[]`` when nothing is common)."""
    if not sequences:
        return []
    common = list(sequences[0])
    for sequence in sequences[1:]:
        limit = 0
        for left, right in zip(common, sequence, strict=False):
            if left != right:
                break
            limit += 1
        common = common[:limit]
    return common


def _boundary_prefix(candidate_parts: Sequence[str], common_tokens: Sequence[str]) -> str:
    """Longest leading token prefix of ``common_tokens`` every candidate extends."""
    for length in range(len(common_tokens), 0, -1):
        prefix = "_".join(common_tokens[:length])
        if all(part.startswith(prefix + "_") for part in candidate_parts):
            return prefix
    return ""


def _apply_hint(prefix: str, hint: str) -> str | None:
    """Resolve ``prefix`` against the device-name hint (Spec §2.3), or ``None``."""
    if prefix == hint:
        return hint
    if prefix.startswith(hint + "_"):
        # Shared entity tokens (e.g. ``lab``) are cut off: the hint is the device.
        return hint
    if prefix.endswith("_" + hint):
        # An area segment in front of the device segment stays part of the ids.
        return prefix
    return None


def resolve_device_slug(
    candidates: Sequence[Mapping[str, object]],
    anchors: Sequence[Mapping[str, object]],
    *,
    hint: str | None,
    device_id: str | None,
) -> DeviceSlugResolution:
    """Resolve the object-id prefix currently used for this person's device.

    ``candidates`` are the entities that will be renamed (F-1/F-2); ``anchors``
    are the remaining entities that carry a ``translation_key`` (their
    object-id suffix is English and language independent, Spec §2.3). Object
    parts only — user labels never influence the result.
    """
    if not candidates:
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_UNRESOLVED)

    anchor_parts = [
        _object_part(str(anchor["entity_id"]))
        for anchor in anchors
        if anchor.get("translation_key") is not None
    ]
    # A single anchor cannot prove where the device segment ends.
    if len(anchor_parts) < 2:
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_UNRESOLVED)

    candidate_parts = [_object_part(str(candidate["entity_id"])) for candidate in candidates]
    common = _common_prefix_sequence([_tokens(part) for part in anchor_parts])
    if not common:
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)

    prefix = _boundary_prefix(candidate_parts, common)
    if not prefix:
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)

    # Divergence test: the token right after the prefix over ALL anchors.
    depth = len(_tokens(prefix))
    suffixes = {(_tokens(part) + [""])[depth] for part in anchor_parts}
    diverges = len(suffixes) > 1

    slug: str | None
    if diverges:
        # ``drinks_today`` vs ``daily_goal_progress``: the prefix is the boundary.
        slug = _apply_hint(prefix, hint) if hint else prefix
        if slug is None:
            return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)
    elif hint:
        # ``lab_crp``/``lab_creatinine``: the suffix token does not diverge, so
        # only the hint can prove the boundary (Spec §2.3).
        slug = _apply_hint(prefix, hint)
        if slug is None:
            return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)
    else:
        # Never guess a device boundary from shared entity tokens.
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_UNRESOLVED)

    if not _SAFE_SLUG_RE.fullmatch(slug):
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)
    if not all(part.startswith(slug + "_") for part in candidate_parts):
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)
    if device_id is not None and any(
        candidate.get("device_id") != device_id for candidate in candidates
    ):
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)
    return DeviceSlugResolution(slug, None)


def build_migration_plan(
    entry_id: str,
    entities: Sequence[Mapping[str, object]],
    *,
    device_slug_hint: str | None,
    device_id: str | None,
    catalog_keys: Collection[str],
    occupied_entity_ids: Collection[str],
) -> MigrationPlan:
    """Pure planning pass: no HA calls, no side effects, stable order.

    ``entities`` are the registry entries of ONE config entry (Spec §3.1);
    ``occupied_entity_ids`` is the global collision set (registry + states).
    """
    materialized = list(entities)
    occupied = set(occupied_entity_ids)

    candidates: list[tuple[Mapping[str, object], int | None, str | None]] = []
    anchors: list[Mapping[str, object]] = []
    for entity in materialized:
        unique_id = str(entity.get("unique_id") or "")
        index = parse_quick_drink_index(unique_id, entry_id)
        key = None if index is not None else parse_custom_lab_key(unique_id, entry_id, catalog_keys)
        if index is None and key is None:
            if entity.get("translation_key") is not None:
                anchors.append(entity)
            continue
        candidates.append((entity, index, key))

    resolution = resolve_device_slug(
        [
            {"entity_id": entity["entity_id"], "device_id": entity.get("device_id")}
            for entity, _index, _key in candidates
        ],
        [
            {
                "entity_id": anchor["entity_id"],
                "translation_key": anchor.get("translation_key"),
                "device_id": anchor.get("device_id"),
            }
            for anchor in anchors
        ],
        hint=device_slug_hint,
        device_id=device_id,
    )

    renames: list[MigrationRename] = []
    skipped: list[MigrationSkip] = []

    if resolution.slug is None:
        reason = resolution.reason or SKIP_DEVICE_SLUG_UNRESOLVED
        for entity, _index, _key in candidates:
            skipped.append(
                MigrationSkip(
                    str(entity.get("unique_id") or ""),
                    str(entity["entity_id"]),
                    None,
                    reason,
                )
            )
        return MigrationPlan(None, tuple(renames), tuple(skipped))

    for entity, index, key in candidates:
        source = str(entity["entity_id"])
        unique_id = str(entity.get("unique_id") or "")
        if index is not None:
            target = f"button.{quick_drink_target(resolution.slug, index)}"
        else:
            if not is_safe_key(key or ""):
                # Never rewrite the key silently: it is part of the unique_id.
                skipped.append(MigrationSkip(unique_id, source, None, SKIP_INVALID_KEY))
                continue
            target = f"sensor.{custom_lab_target(resolution.slug, key or '')}"

        # Checked BEFORE the collision test: `occupied` contains the source id,
        # so an already-migrated entity would otherwise report target_occupied.
        if target == source:
            continue
        if target in occupied:
            skipped.append(MigrationSkip(unique_id, source, target, SKIP_TARGET_OCCUPIED))
            continue
        renames.append(MigrationRename(unique_id, source, target))

    return MigrationPlan(resolution.slug, tuple(renames), tuple(skipped))

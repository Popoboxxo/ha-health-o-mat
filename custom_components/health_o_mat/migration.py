"""HA-free migration logic for the entity id switch (REQ-HOM-130).

Nothing in here imports ``homeassistant`` or the surrounding package: every
function is a pure function over registry data that the caller
(``__init__._async_migrate_entity_ids``) passes in as plain mappings. That keeps
the whole plan unit-testable without a Home Assistant installation (Spec §3.1).

Contract (Spec §3.1): target object ids are derived from the ``unique_id`` only —
never from a display-name slug, never from the system language.

Prefix source (0.17.2): the object-id prefix is derived from the entities that are
about to be renamed (``_sibling_prefix``), so it belongs to them by construction. A
diverging device name, a renamed/unfindable device or a foreign ``device_id`` only
produces a warning; it can never block the pass (0.17.1 production bug). The
structural anchors (catalog lab sensors first) merely confirm or word-boundary-trim
that prefix, and the older anchor/hint heuristic stays as the secondary path for
entries without a usable sibling group.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

SKIP_DEVICE_SLUG_UNRESOLVED = "device_slug_unresolved"
SKIP_DEVICE_SLUG_AMBIGUOUS = "device_slug_ambiguous"
SKIP_TARGET_OCCUPIED = "target_occupied"
SKIP_INVALID_KEY = "invalid_key"
# A user renamed the entity id by hand: their choice wins, the entity is not
# migrated. Reported as a warning, never as a failed pass.
SKIP_CUSTOM_ENTITY_ID = "custom_entity_id"

# Reasons that must NOT block the pass: the entity keeps its id on purpose.
NON_BLOCKING_SKIP_REASONS = frozenset({SKIP_CUSTOM_ENTITY_ID})

# Confirmation mismatches: the sibling prefix (derived from the entities that are
# about to be renamed) disagrees with the device name or the device link. They are
# reported ONCE as a warning and never block the pass (0.17.1 production bug).
WARN_HINT_MISMATCH = "hint_mismatch"
WARN_DEVICE_ID_MISMATCH = "device_id_mismatch"

# A device boundary needs at least two structural entities or two sibling ids:
# a single id can never prove where the device segment ends.
_MIN_SUPPORT = 2
# ``lab_<key>`` translation keys of the catalog markers: their object-id suffix
# comes from catalog-controlled translation text, so it carries no user text.
_CATALOG_LAB_KEY_PREFIX = "lab_"

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
    """Resolved object-id prefix of the person device, or a skip reason.

    ``warnings`` lists non-blocking confirmation mismatches (device name, device
    link): they are reported once by the caller and never change the outcome.
    """

    slug: str | None
    reason: str | None
    warnings: tuple[str, ...] = ()


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
    """Deterministic, side-effect-free result of one planning pass.

    ``warnings`` carries non-blocking confirmation mismatches of the resolved
    prefix; the caller reports them ONCE and continues.
    """

    device_slug: str | None
    renames: tuple[MigrationRename, ...]
    skipped: tuple[MigrationSkip, ...]
    warnings: tuple[str, ...] = ()


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


def _supported_prefix_sequence(sequences: Sequence[Sequence[str]]) -> list[str] | None:
    """Longest leading token sequence shared by at least TWO sequences.

    A single outlier must not erase the prefix: one hand-renamed entity id
    (``sensor.caro_gewicht`` next to ``sensor.health_o_mat_caro_*``) shares no
    leading token with the rest and would otherwise empty the common prefix of
    every anchor (Spec §2.3, production bug ``device_slug_ambiguous``).

    Returns ``None`` when two *different* prefixes are equally long and equally
    supported — that is genuine ambiguity, not a guess.
    """
    support: dict[tuple[str, ...], int] = {}
    for sequence in sequences:
        for length in range(1, len(sequence) + 1):
            prefix = tuple(sequence[:length])
            support[prefix] = support.get(prefix, 0) + 1

    supported = [prefix for prefix, count in support.items() if count >= 2]
    if not supported:
        return []
    longest = max(len(prefix) for prefix in supported)
    winners = [prefix for prefix in supported if len(prefix) == longest]
    if len(winners) > 1:
        return None
    return list(winners[0])


def _boundary_prefix(candidate_parts: Sequence[str], common_tokens: Sequence[str]) -> str:
    """Trim the anchor prefix to the part the candidate ids actually share.

    Shared entity tokens (e.g. ``lab``) are cut off when the candidates are
    ``…_max_vitamin_d`` but the anchors are ``…_max_lab_crp``. Only candidates
    that start like the anchor prefix are consulted (a hand-renamed id shares
    no leading token and must not erase the prefix), and a strict majority of
    them has to extend the prefix — so one outlier cannot shorten it either.
    """
    first = common_tokens[0]
    relevant = [part for part in candidate_parts if _tokens(part)[:1] == [first]]
    if not relevant:
        return "_".join(common_tokens)
    for length in range(len(common_tokens), 0, -1):
        prefix = "_".join(common_tokens[:length])
        extending = sum(1 for part in relevant if part.startswith(prefix + "_"))
        if extending * 2 > len(relevant):
            return prefix
    return ""


def _supporting_anchors(anchor_parts: Sequence[str], slug: str) -> list[str]:
    """Anchors whose object id starts with ``slug`` (Spec §2.3)."""
    return [part for part in anchor_parts if part == slug or part.startswith(slug + "_")]


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


def _common_token_prefix(sequences: Sequence[Sequence[str]]) -> list[str]:
    """Longest leading token sequence shared by EVERY sequence."""
    if not sequences:
        return []
    common: list[str] = []
    for index, token in enumerate(sequences[0]):
        if all(len(sequence) > index and sequence[index] == token for sequence in sequences[1:]):
            common.append(token)
        else:
            break
    return common


def _sibling_prefix(entity_ids: Sequence[str]) -> str | None:
    """Object-id prefix shared by the ids that are about to be renamed.

    The prefix comes from the migration candidates themselves, so it belongs to
    the entities being renamed *by construction* — no device name, no hint and no
    foreign ``device_id`` can move or block it (0.17.1 production bug: a renamed
    device or a diverging hint left all four buttons on
    ``device_slug_ambiguous``).

    A completely hand-renamed id (``button.mein_wasser``) forms its own
    first-token group and can never erase the prefix of the majority group; such
    an id is reported as ``custom_entity_id`` later. ``None`` means: no group of
    two ids shares a non-empty prefix, or two groups are equally large — both are
    genuine ambiguity, never a guess.
    """
    groups: dict[str, list[list[str]]] = {}
    for entity_id in entity_ids:
        tokens = _tokens(_object_part(entity_id))
        if tokens:
            groups.setdefault(tokens[0], []).append(tokens)

    supported = [members for members in groups.values() if len(members) >= 2]
    if not supported:
        return None
    largest = max(len(members) for members in supported)
    winners = [members for members in supported if len(members) == largest]
    if len(winners) != 1:
        return None
    members = winners[0]

    common = _common_token_prefix(members)
    # A prefix that swallows a whole id is an entity name, not a device segment.
    while common and any(len(tokens) <= len(common) for tokens in members):
        common.pop()
    if not common:
        return None
    prefix = "_".join(common)
    if not _SAFE_SLUG_RE.fullmatch(prefix):
        return None
    return prefix


def _is_catalog_lab_key(translation_key: object, catalog_keys: Collection[str]) -> bool:
    """True for the ``lab_<key>`` translation key of a CATALOG lab marker."""
    return (
        isinstance(translation_key, str)
        and translation_key.startswith(_CATALOG_LAB_KEY_PREFIX)
        and translation_key[len(_CATALOG_LAB_KEY_PREFIX) :] in catalog_keys
    )


def _structural_parts(
    anchors: Sequence[Mapping[str, object]], catalog_keys: Collection[str]
) -> tuple[list[str], list[str]]:
    """Object parts of the entry's structural entities.

    Returns ``(catalog lab sensors, all translation-key entities)``. The catalog
    lab sensors are the primary structural source: their object-id suffix is the
    catalog key, so it can never contain user text.
    """
    catalog: list[str] = []
    every: list[str] = []
    for anchor in anchors:
        translation_key = anchor.get("translation_key")
        if translation_key is None:
            continue
        part = _object_part(str(anchor["entity_id"]))
        every.append(part)
        if _is_catalog_lab_key(translation_key, catalog_keys):
            catalog.append(part)
    return catalog, every


def _trimmed_prefix(tokens: Sequence[str], parts: Sequence[str]) -> str | None:
    """Longest proper prefix of ``tokens`` that at least two structural ids share.

    Four buttons labelled ``Glas Wasser``/``Glas Saft`` share the label token, so
    the raw sibling prefix ends in user text; the structural entities prove where
    the device segment really ends. Only called when the raw prefix is NOT
    confirmed, so trimming can never shorten an already proven boundary.
    """
    for length in range(len(tokens) - 1, 0, -1):
        prefix = "_".join(tokens[:length])
        if len(_supporting_anchors(parts, prefix)) >= _MIN_SUPPORT:
            return prefix
    return None


def _sibling_resolution(
    slug: str,
    candidates: Sequence[Mapping[str, object]],
    *,
    hint: str | None,
    device_id: str | None,
) -> DeviceSlugResolution:
    """Accept a sibling-derived slug; diverging hint/device link only warn."""
    warnings: list[str] = []
    if hint is not None and _apply_hint(slug, hint) is None:
        warnings.append(WARN_HINT_MISMATCH)
    if device_id is not None and any(
        candidate.get("device_id") != device_id for candidate in candidates
    ):
        warnings.append(WARN_DEVICE_ID_MISMATCH)
    return DeviceSlugResolution(slug, None, tuple(warnings))


def _resolve_sibling_slug(
    candidates: Sequence[Mapping[str, object]],
    catalog_parts: Sequence[str],
    anchor_parts: Sequence[str],
    *,
    hint: str | None,
    device_id: str | None,
) -> DeviceSlugResolution | None:
    """Primary path: prefix from the candidates, confirmed by structural ids.

    ``None`` means "not derivable this way" and hands over to the anchor path —
    never a failure on its own, so a missing/renamed device or a single outlier
    cannot block the pass.
    """
    sibling = _sibling_prefix([str(candidate["entity_id"]) for candidate in candidates])
    if sibling is None:
        return None
    sources = [parts for parts in (catalog_parts, anchor_parts) if len(parts) >= _MIN_SUPPORT]
    for parts in sources:
        if len(_supporting_anchors(parts, sibling)) >= _MIN_SUPPORT:
            return _sibling_resolution(sibling, candidates, hint=hint, device_id=device_id)
    # Word-boundary trimming needs suffix evidence that cannot contain user text:
    # only the catalog lab sensors qualify (their suffix is a catalog key). The
    # fallback over all translation-key entities is used for confirmation only,
    # so an already-migrated sibling group (`…_quick_drink_<n>`) is never trimmed
    # into an arbitrary device boundary.
    trimmed = _trimmed_prefix(_tokens(sibling), catalog_parts)
    if trimmed is not None:
        return _sibling_resolution(trimmed, candidates, hint=hint, device_id=device_id)
    return None


def resolve_device_slug(
    candidates: Sequence[Mapping[str, object]],
    anchors: Sequence[Mapping[str, object]],
    *,
    hint: str | None,
    device_id: str | None,
    catalog_keys: Collection[str] = (),
) -> DeviceSlugResolution:
    """Resolve the object-id prefix currently used for this person's device.

    ``candidates`` are the entities that will be renamed (F-1/F-2); ``anchors``
    are the remaining entities that carry a ``translation_key`` (their
    object-id suffix is English and language independent, Spec §2.3). Object
    parts only — user labels never influence the result.

    Primary source is the sibling prefix of the candidates (``_sibling_prefix``):
    it is derived from the entities that are going to be renamed, so hint, device
    name and ``device_id`` can no longer block the pass — they are at most
    warnings. The structural anchors only confirm or word-boundary-trim that
    prefix; the anchor/hint heuristic stays as the secondary path for entries
    without usable siblings.

    Acceptance (Spec §2.3): the prefix is non-empty, slug-safe and supported by
    at least two structural ids (or two sibling ids plus one confirming source).
    It is NOT required that every registry entity starts with it: a hand-renamed
    entity id is the user's choice and is skipped as ``custom_entity_id``.
    """
    if not candidates:
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_UNRESOLVED)

    catalog_parts, anchor_parts = _structural_parts(anchors, catalog_keys)

    sibling = _resolve_sibling_slug(
        candidates, catalog_parts, anchor_parts, hint=hint, device_id=device_id
    )
    if sibling is not None:
        return sibling

    # A single anchor cannot prove where the device segment ends.
    if len(anchor_parts) < 2:
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_UNRESOLVED)

    common = _supported_prefix_sequence([_tokens(part) for part in anchor_parts])
    if common is None or not common:
        # Two equally supported prefixes, or no prefix shared by two anchors.
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)

    candidate_parts = [_object_part(str(candidate["entity_id"])) for candidate in candidates]
    prefix = _boundary_prefix(candidate_parts, common)
    if not prefix:
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)

    supporting = _supporting_anchors(anchor_parts, prefix)
    if len(supporting) < 2:
        return DeviceSlugResolution(None, SKIP_DEVICE_SLUG_AMBIGUOUS)

    # Divergence test: the token right after the prefix over the supporting anchors.
    depth = len(_tokens(prefix))
    suffixes = {(_tokens(part) + [""])[depth] for part in supporting}
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
    if len(_supporting_anchors(anchor_parts, slug)) < 2:
        # Nothing but the anchors may confirm the boundary (fail-closed).
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
        catalog_keys=catalog_keys,
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
        if not _object_part(source).startswith(resolution.slug + "_"):
            # Hand-renamed entity id: the user's id wins, nothing is rewritten.
            skipped.append(MigrationSkip(unique_id, source, None, SKIP_CUSTOM_ENTITY_ID))
            continue
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

    return MigrationPlan(resolution.slug, tuple(renames), tuple(skipped), resolution.warnings)

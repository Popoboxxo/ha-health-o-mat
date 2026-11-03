"""E2E: config-entry migration with an existing entry (REQ-HOM-101 AK 4).

AK 4 of REQ-HOM-101 asks for the one thing the unit suite cannot prove: an
**update with pre-existing data** — a v1 config entry (quick drinks in
``entry.data``, ``options`` empty, entity ids still derived from the drink
labels) that HA itself loads, migrates and keeps usable. The unit tests
(``tests/test_wave_a.py:218-241``, ``tests/test_entry_migration.py``) feed
``async_migrate_entry`` hand-built mocks; here the real instance runs the real
migration at setup time.

Two scenarios, one module — they are the two halves of the same acceptance
criterion (the plan's B-1 + B-2, ``docs/PLAN-AUDIT-2026-11-03.md:203-204``):

* **legacy entry** — the entry is downgraded to version 1 in HA's own storage
  (``.storage/core.config_entries``) and its four quick-drink registry entries
  are put back on their label-derived ids (``…_glas_wasser``), exactly what a
  ≤ 0.16.2 install looks like. After HA restarts, the entry must be at version 3
  with ``options.quick_drinks`` filled and ``data`` cleaned, the four buttons
  must exist under their **new** ids (renamed, not duplicated, not lost), and a
  drink booked before the downgrade must still be there (no data loss).
* **quick-drink change after reload** — a slot is changed through the real
  options flow, the entry is reloaded, and the button must keep its
  ``unique_id``/``entity_id`` while its label and the amount it books follow the
  new option value.

Why the storage manipulation is legitimate: a v1 entry cannot be produced
through the config flow of a current installation (``ConfigFlow.VERSION`` is 3).
The plan explicitly sanctions this fixture (``docs/PLAN-AUDIT-2026-11-03.md``,
WP-B step 1: "``.storage/core.config_entries`` im Compose-Volume vor dem Start
auf Version 1 zurückschreiben"), only the throwaway person's own records are
touched, and the person is deleted again in ``finally``. The storage documents
are deliberately not restored afterwards: replaying a pre-test entity registry
would resurrect rows for the deleted entry.

This module **stops, patches and restarts** the instance, so it refuses to run
against the shared dev instance (``/home/hermes/ha-test``, loopback:8123) — see
the import-time guard below. Inside the Compose ``e2e`` runner container there is
no Docker socket and no ``/config`` bind mount; the scenarios skip there with an
explicit reason instead of pretending to pass.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import tempfile
import time
from typing import Any

import pytest
import requests
from e2e_helpers import (
    ALLOW_SHARED_ENV,
    compose_container,
    host_config_dir,
    is_shared_dev_instance,
    start_home_assistant,
    stop_home_assistant,
    wait_for,
    wait_for_entry_loaded,
    wait_for_instance_ready,
    ws_command,
)

from scripts.e2e_bootstrap import _headers, _post_json, ensure_person

pytestmark = pytest.mark.e2e

# Throwaway persons, one per scenario (created through the real config flow and
# deleted again in `finally`, so repeated runs stay independent).
PERSON_LEGACY = "E2E-Legacy"
PERSON_RELOAD = "E2E-Reload"

# Device name "Health-O-Mat E2E-Legacy" -> object-id prefix of every entity.
LEGACY_PREFIX = "health_o_mat_e2e_legacy"
RELOAD_PREFIX = "health_o_mat_e2e_reload"

# The four quick-drink slots; index 0..3 is part of the `unique_id` and stable
# across the whole version history (`button.py`, `key = f"button_quick_{i}"`).
QUICK_KEYS = tuple(f"button_quick_{i}" for i in range(4))
LEGACY_ENTITY_IDS = (
    # Pre-0.16.2 shape: object id derived from the drink label ("Glas Wasser").
    f"button.{LEGACY_PREFIX}_glas_wasser",
    f"button.{LEGACY_PREFIX}_flasche_wasser",
    f"button.{LEGACY_PREFIX}_tasse_kaffee",
    f"button.{LEGACY_PREFIX}_glas_saft",
)
MIGRATED_ENTITY_IDS = tuple(f"button.{LEGACY_PREFIX}_quick_drink_{i + 1}" for i in range(4))

# What a genuine v1 entry (<= v0.4.0) wrote into `entry.data`: the hard-wired
# default slots of that release (`git show v0.4.0:…/config_flow.py`,
# `git show v0.4.0:…/const.py`). Reproduced verbatim so the "no data loss"
# assertion compares against the shape the migration was written for.
LEGACY_QUICK_DRINKS = [
    {"key": "glas_wasser", "label": "Glas Wasser", "ml": 200, "icon": "mdi:glass-water"},
    {"key": "flasche_wasser", "label": "Flasche Wasser", "ml": 500, "icon": "mdi:bottle-water"},
    {"key": "kaffee", "label": "Tasse Kaffee", "ml": 250, "icon": "mdi:coffee"},
    {"key": "saft", "label": "Glas Saft", "ml": 200, "icon": "mdi:fruit-citrus"},
]

# The changed slot: label AND amount change, so the button press proves the new
# `ml`, not just the new text.
CHANGED_INDEX = 1
CHANGED_LABEL = "Kanne Tee"
CHANGED_ML = 640

# Import-time guard, not a fixture: this module stops the instance and rewrites
# its storage. Checking at import is the only point guaranteed to precede every
# write; `pytest.skip` keeps the refusal visible instead of silently green.
if (
    is_shared_dev_instance(os.environ.get("HASS_BASE_URL", "http://localhost:8123"))
    and os.environ.get(ALLOW_SHARED_ENV) != "1"
):
    pytest.skip(
        "test_config_migration_e2e stops the instance and rewrites .storage — it"
        " refuses to run against the shared dev instance (loopback:8123)."
        " Point HASS_BASE_URL at the Compose stack (E2E_HA_PORT, default 8124)"
        f" or set {ALLOW_SHARED_ENV}=1 if that really is a throwaway stack.",
        allow_module_level=True,
    )


# --- HA API helpers --------------------------------------------------------


def _state(base_url: str, token: str, entity_id: str) -> dict[str, Any] | None:
    """One entity state, or None when the entity is not in the state machine."""
    response = requests.get(
        f"{base_url}/api/states/{entity_id}", headers=_headers(token), timeout=30
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _call_service(
    base_url: str, token: str, domain: str, service: str, data: dict[str, Any]
) -> None:
    """Call a real HA service (the path a user or an automation triggers)."""
    response = requests.post(
        f"{base_url}/api/services/{domain}/{service}",
        headers=_headers(token),
        json=data,
        timeout=60,
    )
    response.raise_for_status()


def _registry_rows(base_url: str, token: str, entry_id: str) -> list[dict[str, Any]]:
    """Entity-registry rows owned by one config entry.

    Read over the websocket (`config/entity_registry/list`) like the rest of the
    suite: there is no stable REST equivalent, and `ws_command` already retries
    the transient reload window the options save opens.
    """
    registry = ws_command(base_url, token, {"type": "config/entity_registry/list"}) or []
    return [row for row in registry if row.get("config_entry_id") == entry_id]


def _quick_rows(base_url: str, token: str, entry_id: str) -> dict[str, dict[str, Any]]:
    """`unique_id -> registry row` for the four quick-drink buttons."""
    wanted = {f"{entry_id}_{key}" for key in QUICK_KEYS}
    return {
        str(row["unique_id"]): row
        for row in _registry_rows(base_url, token, entry_id)
        if row.get("unique_id") in wanted
    }


def _wait_quick_rows(base_url: str, token: str, entry_id: str) -> dict[str, dict[str, Any]]:
    """Poll until all four quick-drink buttons are registered."""
    return wait_for(
        lambda: _quick_rows(base_url, token, entry_id),
        lambda rows: len(rows) == len(QUICK_KEYS),
        "the four quick-drink buttons to be registered",
    )


def _drinks_today(base_url: str, token: str, entity_id: str) -> dict[str, float]:
    """`drinks_today` of one person: the window's volume and its booking count.

    The entity's *state* is the ml total (``TodaySensor.native_value``); the
    number of bookings is the ``drinks_count`` attribute. Both come from the
    same on-read window (REQ-HOM-001), so they are read together.
    """
    state = _state(base_url, token, entity_id)
    assert state is not None, f"{entity_id} is not in the state machine"
    attributes = state.get("attributes") or {}
    return {
        "ml": float(state["state"]),
        "count": float(attributes.get("drinks_count", 0)),
    }


def _entry_options_flow_id(base_url: str, token: str, entry_id: str) -> str:
    """Open the real options-flow menu (REQ-HOM-119) and return its flow id."""
    flow = _post_json(
        f"{base_url}/api/config/config_entries/options/flow", token, {"handler": entry_id}
    )
    assert flow.get("type") == "menu", f"expected the options menu, got {flow!r}"
    return str(flow["flow_id"])


def _change_quick_drink(
    base_url: str,
    token: str,
    entry_id: str,
    index: int,
    *,
    label: str,
    ml: int,
) -> None:
    """Change one quick-drink slot through the real options flow and save.

    Navigation is the one the UI takes for "only the drinks section": ``init``
    (menu) → ``drinks`` → ``summary``. Every other field is submitted with the
    value the form itself offered, so the flow persists exactly one change (the
    lexicon is part of the same form and must round-trip unchanged).
    """
    base = f"{base_url}/api/config/config_entries/options/flow"
    flow_id = _entry_options_flow_id(base_url, token, entry_id)

    form = _post_json(f"{base}/{flow_id}", token, {"next_step_id": "drinks"})
    assert form.get("type") == "form" and form.get("step_id") == "drinks", form
    assert not form.get("errors"), form

    payload = {
        field["name"]: field["default"] for field in form["data_schema"] if "default" in field
    }
    payload[f"quick_{index}_label"] = label
    payload[f"quick_{index}_ml"] = ml

    menu = _post_json(f"{base}/{flow_id}", token, payload)
    assert menu.get("type") == "menu", f"expected the menu after saving drinks, got {menu!r}"

    summary = _post_json(f"{base}/{flow_id}", token, {"next_step_id": "summary"})
    assert summary.get("type") == "form" and summary.get("step_id") == "summary", summary

    created = _post_json(f"{base}/{flow_id}", token, {})
    assert created.get("type") == "create_entry", f"options flow did not save: {created!r}"


def _reload_entry(base_url: str, token: str, entry_id: str) -> None:
    """Reload one config entry (what "Reload" in the UI does)."""
    response = requests.post(
        f"{base_url}/api/config/config_entries/entry/{entry_id}/reload",
        headers=_headers(token),
        timeout=60,
    )
    response.raise_for_status()
    assert response.json() == {"require_restart": False}, response.json()


def _friendly_name(base_url: str, token: str, entity_id: str) -> str:
    """The served friendly name of one entity (empty string when absent)."""
    state = _state(base_url, token, entity_id)
    if state is None:
        return ""
    return str(state.get("attributes", {}).get("friendly_name") or "")


# --- storage helpers (host bind mount) -------------------------------------


def _read_storage(config_dir: pathlib.Path, name: str) -> dict[str, Any]:
    """Read one HA `.storage` document from the host bind mount."""
    return json.loads((config_dir / ".storage" / name).read_text(encoding="utf-8"))


def _entry_record(config_dir: pathlib.Path, entry_id: str) -> dict[str, Any]:
    """This person's config-entry record (version, data, options)."""
    document = _read_storage(config_dir, "core.config_entries")
    matches = [item for item in document["data"]["entries"] if item["entry_id"] == entry_id]
    assert len(matches) == 1, f"expected exactly one config entry {entry_id}, got {len(matches)}"
    return matches[0]


def _store_record(config_dir: pathlib.Path, entry_id: str) -> dict[str, Any]:
    """This person's record in the shared Health-O-Mat store."""
    document = _read_storage(config_dir, "health_o_mat")
    return document["data"]["entries"].get(entry_id) or {}


def _image_of(container: str) -> str:
    """Image of the running E2E container — same image as the stack itself."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.Config.Image}}", container],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, f"docker inspect {container} failed: {result.stderr.strip()}"
    return result.stdout.strip()


#: Runs *inside* a throwaway container as root, with HA's `/config` bind-mounted.
#: It rewrites exactly two documents and nothing else; `payload` arrives on stdin.
_PATCH_SCRIPT = """
import json
import pathlib
import sys

payload = json.load(sys.stdin)
storage = pathlib.Path("/config/.storage")


def load(name):
    return json.loads((storage / name).read_text(encoding="utf-8"))


def save(name, document):
    target = storage / name
    temporary = target.with_name(target.name + ".e2e-tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)


entries = load("core.config_entries")
found = 0
for entry in entries["data"]["entries"]:
    if entry["entry_id"] != payload["entry_id"]:
        continue
    found += 1
    entry["version"] = payload["version"]
    entry["data"] = payload["data"]
    entry["options"] = payload["options"]
if found != 1:
    raise SystemExit(
        "expected exactly one config entry %s, found %d"
        % (payload["entry_id"], found)
    )
save("core.config_entries", entries)

registry = load("core.entity_registry")
by_unique = {row["unique_id"]: row for row in registry["data"]["entities"]}
for unique_id, spec in payload["entities"].items():
    row = by_unique.get(unique_id)
    if row is None:
        raise SystemExit("registry entry %s not found" % unique_id)
    row["entity_id"] = spec["entity_id"]
    row["object_id_base"] = spec["object_id_base"]
    row["original_name"] = spec["original_name"]
save("core.entity_registry", registry)
"""


def _patch_storage(config_dir: pathlib.Path, container: str, payload: dict[str, Any]) -> None:
    """Downgrade one entry + its entity ids while HA is stopped.

    Runs a throwaway container with the config bind mount because `.storage` is
    owned by root and the host user cannot write it. `--rm` is safe here: the
    output is captured synchronously by `subprocess.run`, so a failure still
    carries the diagnostics (the container is never needed for post-mortem).
    """
    script = _PATCH_SCRIPT
    with tempfile.TemporaryDirectory(prefix="hom-e2e-patch-") as temp:
        path = pathlib.Path(temp) / "patch_storage.py"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "-v",
                f"{config_dir}:/config:rw",
                "-v",
                f"{path}:/patch_storage.py:ro",
                "--entrypoint",
                "python3",
                _image_of(container),
                "/patch_storage.py",
            ],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    assert result.returncode == 0, (
        "patching HA storage failed (rc="
        f"{result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
    )


# --- tests -----------------------------------------------------------------


def test_req_hom_101_ak4_legacy_entry_migrates_without_losing_quick_drinks(
    hass_base_url, hass_bearer_token
):
    """[REQ-HOM-101] AK 4: a v1 entry with existing data survives the update.

    Asserts, in this order:

    1. the drink booked *before* the downgrade is still counted afterwards
       (no data loss through the entry migration),
    2. the entry is migrated to version 3, ``options.quick_drinks`` carries the
       v1 slots and ``entry.data`` no longer does,
    3. the four quick-drink buttons were **renamed** to their stable ids — no
       duplicate, none left behind on the old label-derived id,
    4. a later options change (slot 1 label + ml) plus an explicit reload makes
       the same four buttons serve the new label and book the new amount.
    """
    container = compose_container(hass_base_url)
    config_dir = host_config_dir(hass_base_url)
    if container is None or config_dir is None:
        pytest.skip(
            "legacy-entry migration needs to stop the instance and rewrite .storage:"
            " no Docker control or /config bind mount available (the Compose `e2e`"
            " runner container has neither). Run it from the host with"
            " HASS_BASE_URL=http://127.0.0.1:8124."
        )

    person = ensure_person(hass_base_url, hass_bearer_token, PERSON_LEGACY, enable_panel=False)
    entry_id = str(person["entry_id"])

    drinks_sensor = f"sensor.{LEGACY_PREFIX}_drinks_today"
    quick_entity_ids = [f"button.{LEGACY_PREFIX}_quick_drink_{i + 1}" for i in range(4)]
    try:
        # The bootstrap's options save reloads the entry (quick-drink set).
        wait_for_entry_loaded(hass_base_url, hass_bearer_token, entry_id)
        _wait_quick_rows(hass_base_url, hass_bearer_token, entry_id)

        # 1) Existing data: one drink, booked through the real button.
        _call_service(
            hass_base_url,
            hass_bearer_token,
            "button",
            "press",
            {"entity_id": quick_entity_ids[0]},
        )
        wait_for(
            lambda: _drinks_today(hass_base_url, hass_bearer_token, drinks_sensor),
            lambda today: today["count"] == 1,
            "the drink booked before the downgrade",
        )
        booked = wait_for(
            lambda: (_store_record(config_dir, entry_id).get("drinks") or [{}])[-1],
            lambda drink: bool(drink.get("ml")),
            "the booked drink in the store file",
        )
        booked_ml = booked["ml"]

        # 2) Downgrade to what a <= 0.16.2 installation looks like.
        stop_home_assistant(container)
        try:
            _patch_storage(
                config_dir,
                container,
                {
                    "entry_id": entry_id,
                    "version": 1,
                    "data": {"person": PERSON_LEGACY, "quick_drinks": LEGACY_QUICK_DRINKS},
                    "options": {},
                    "entities": {
                        f"{entry_id}_{key}": {
                            "entity_id": legacy_id,
                            "object_id_base": legacy_id.split(".", 1)[1].removeprefix(
                                f"{LEGACY_PREFIX}_"
                            ),
                            "original_name": LEGACY_QUICK_DRINKS[index]["label"],
                        }
                        for index, (key, legacy_id) in enumerate(
                            zip(QUICK_KEYS, LEGACY_ENTITY_IDS, strict=True)
                        )
                    },
                },
            )
        finally:
            start_home_assistant(container, hass_base_url)

        ready = wait_for_instance_ready(
            hass_base_url,
            hass_bearer_token,
            [drinks_sensor, *quick_entity_ids],
        )
        assert ready[drinks_sensor]["state"] not in ("unavailable", "unknown"), ready[drinks_sensor]

        # 1) The pre-downgrade drink is still there — the migration is additive
        #    for the store (it is keyed by the unchanged entry_id).
        assert _drinks_today(hass_base_url, hass_bearer_token, drinks_sensor)["count"] == 1
        assert _store_record(config_dir, entry_id)["drinks"][-1]["ml"] == booked_ml

        # 2) Data -> options, version 3. Polled: HA persists `.storage` with a
        #    delayed save, so the file lags the in-memory migration by a few
        #    seconds — a single read would be a race, not an assertion.
        record = wait_for(
            lambda: _entry_record(config_dir, entry_id),
            lambda item: item.get("version") == 3,
            "the config entry to be migrated to version 3 and persisted",
            timeout=90,
        )
        assert "quick_drinks" not in record["data"], record["data"]
        assert set(record["data"]) == {"person"}, record["data"]
        assert record["options"]["quick_drinks"] == LEGACY_QUICK_DRINKS, record["options"]

        # 3) Renamed, not duplicated and not lost.
        rows = _wait_quick_rows(hass_base_url, hass_bearer_token, entry_id)
        assert sorted(rows) == sorted(f"{entry_id}_{key}" for key in QUICK_KEYS), sorted(rows)
        assert sorted(row["entity_id"] for row in rows.values()) == sorted(MIGRATED_ENTITY_IDS)
        registration = _registry_rows(hass_base_url, hass_bearer_token, entry_id)
        old_ids = {row["entity_id"] for row in registration} & set(LEGACY_ENTITY_IDS)
        assert not old_ids, f"label-derived entity ids survived the migration: {sorted(old_ids)}"

        # 4) A later options change plus reload is served by the same entities.
        _change_quick_drink(
            hass_base_url,
            hass_bearer_token,
            entry_id,
            CHANGED_INDEX,
            label=CHANGED_LABEL,
            ml=CHANGED_ML,
        )
        # The save itself reloads the entry; wait it out before the explicit
        # reload below so the button press cannot land in either window.
        wait_for_entry_loaded(hass_base_url, hass_bearer_token, entry_id)
        _reload_entry(hass_base_url, hass_bearer_token, entry_id)
        changed_entity_id = quick_entity_ids[CHANGED_INDEX]
        wait_for(
            lambda: _friendly_name(hass_base_url, hass_bearer_token, changed_entity_id),
            lambda name: name.endswith(CHANGED_LABEL),
            "the migrated button to show the changed label",
        )
        after = _wait_quick_rows(hass_base_url, hass_bearer_token, entry_id)
        assert {key: row["entity_id"] for key, row in after.items()} == {
            key: row["entity_id"] for key, row in rows.items()
        }, "reload changed an entity id"

        _call_service(
            hass_base_url,
            hass_bearer_token,
            "button",
            "press",
            {"entity_id": changed_entity_id},
        )
        wait_for(
            lambda: _drinks_today(hass_base_url, hass_bearer_token, drinks_sensor),
            lambda today: today["count"] == 2,
            "the drink booked after the options change",
        )
        assert _store_record(config_dir, entry_id)["drinks"][-1]["ml"] == CHANGED_ML
    finally:
        # Never leave the instance down, then drop the throwaway person. The
        # storage documents are NOT restored: the entry is deleted instead, and
        # replaying a pre-test registry would resurrect rows for a deleted entry.
        if container is not None and _is_stopped(container):
            start_home_assistant(container, hass_base_url)
        _delete_entry_safely(hass_base_url, hass_bearer_token, entry_id)


def test_req_hom_101_ak4_quick_drink_change_is_served_after_entry_reload(
    hass_base_url, hass_bearer_token
):
    """[REQ-HOM-101] AK 4: button identity is stable, label and amount follow options.

    This is the "update with existing data" half of B-2: the entry already has a
    store record and a registered button. Changing slot 1 must not re-register
    anything (``unique_id`` AND ``entity_id`` stay), must show the new label, and
    pressing the button must book the new amount — the label/amount pair is read
    from ``entry.options`` when the entity is built, so a reload is what makes
    it actionable.
    """
    person = ensure_person(
        hass_base_url,
        hass_bearer_token,
        PERSON_RELOAD,
        enable_panel=False,
    )
    entry_id = str(person["entry_id"])
    try:
        # The bootstrap's options save reloads the entry (quick-drink set).
        wait_for_entry_loaded(hass_base_url, hass_bearer_token, entry_id)
        before = _wait_quick_rows(hass_base_url, hass_bearer_token, entry_id)
        drinks_sensor = f"sensor.{RELOAD_PREFIX}_drinks_today"
        changed_entity_id = before[f"{entry_id}_button_quick_{CHANGED_INDEX}"]["entity_id"]

        _change_quick_drink(
            hass_base_url,
            hass_bearer_token,
            entry_id,
            CHANGED_INDEX,
            label=CHANGED_LABEL,
            ml=CHANGED_ML,
        )
        # The save itself reloads the entry; wait it out before the explicit
        # reload below so the button press cannot land in either window.
        wait_for_entry_loaded(hass_base_url, hass_bearer_token, entry_id)
        _reload_entry(hass_base_url, hass_bearer_token, entry_id)

        wait_for(
            lambda: _friendly_name(hass_base_url, hass_bearer_token, changed_entity_id),
            lambda name: name.endswith(CHANGED_LABEL),
            "the button to show the changed label after the reload",
        )

        after = _wait_quick_rows(hass_base_url, hass_bearer_token, entry_id)
        assert sorted(after) == sorted(before), "the reload changed the set of quick-drink buttons"
        assert {key: row["entity_id"] for key, row in after.items()} == {
            key: row["entity_id"] for key, row in before.items()
        }, "the reload changed an entity id (REQ-HOM-130 regression)"
        assert after[f"{entry_id}_button_quick_{CHANGED_INDEX}"]["original_name"] == CHANGED_LABEL

        _call_service(
            hass_base_url,
            hass_bearer_token,
            "button",
            "press",
            {"entity_id": changed_entity_id},
        )
        today = wait_for(
            lambda: _drinks_today(hass_base_url, hass_bearer_token, drinks_sensor),
            lambda value: value["count"] == 1,
            "the drink booked by the changed button",
        )
        assert today["ml"] == CHANGED_ML, today
    finally:
        _delete_entry_safely(hass_base_url, hass_bearer_token, entry_id)


def _is_stopped(container: str) -> bool:
    """Whether the container exists but is not running."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", container],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "false"


def _delete_entry_safely(base_url: str, token: str, entry_id: str) -> None:
    """Remove one config entry; already-gone is fine (cleanup must not mask a failure)."""
    deadline = time.monotonic() + 60
    last = "no attempt"
    while time.monotonic() < deadline:
        response = requests.delete(
            f"{base_url}/api/config/config_entries/entry/{entry_id}",
            headers=_headers(token),
            timeout=30,
        )
        if response.status_code in (200, 404):
            return
        last = f"HTTP {response.status_code}: {response.text}"
        time.sleep(1.0)
    raise AssertionError(f"could not delete config entry {entry_id}: {last}")

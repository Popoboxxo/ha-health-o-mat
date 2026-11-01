"""Tests for `scripts/e2e_bootstrap.py`: credential handling (admin gate, #28).

Two properties of the bootstrap are load-bearing for the E2E suite and are
cheap to pin without a running Home Assistant:

* the CLI output path (stdout / `--json-out`) never carries a token or password,
* the `is_admin` flag reported for the non-admin fixture is DERIVED from the
  user's group list instead of being a constant — otherwise
  `test_admin_gate_e2e.py` would only assert itself.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("requests")
pytest.importorskip("websockets.sync.client")

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = _load_module("e2e_bootstrap_under_test", _REPO_ROOT / "scripts" / "e2e_bootstrap.py")


def _auth_user(group_ids: list[str]) -> dict:
    return {"id": "user-42", "username": "e2e-nonadmin", "group_ids": group_ids}


# --- redaction (stdout / --json-out) ----------------------------------------


def test_redact_secrets_drops_every_token_and_password_recursively():
    state = {
        "base_url": "http://localhost:8124",
        "username": "e2e",
        "token": "live-admin-token",
        "non_admin": {
            "username": "e2e-nonadmin",
            "password": "live-non-admin-password",
            "token": "live-non-admin-token",
            "group_ids": ["system-users"],
            "is_admin": False,
        },
        "persons": {"E2E-Deep": {"entry_id": "abc", "token": "nested-token"}},
    }

    redacted = bootstrap.redact_secrets(state)

    assert redacted["base_url"] == "http://localhost:8124"
    assert redacted["username"] == "e2e"
    assert "token" not in redacted
    assert "password" not in redacted["non_admin"]
    assert "token" not in redacted["non_admin"]
    assert redacted["non_admin"]["group_ids"] == ["system-users"]
    assert redacted["persons"]["E2E-Deep"] == {"entry_id": "abc"}

    serialized = json.dumps(redacted)
    for secret in (
        "live-admin-token",
        "live-non-admin-password",
        "live-non-admin-token",
        "nested-token",
    ):
        assert secret not in serialized


def test_redact_secrets_keeps_scalars_and_lists_intact():
    assert bootstrap.redact_secrets(["a", 1, None]) == ["a", 1, None]
    assert bootstrap.redact_secrets("plain") == "plain"


# --- non-admin user (F4: no tautological is_admin) --------------------------


def test_ensure_non_admin_user_derives_admin_flag_and_omits_password(monkeypatch):
    monkeypatch.setattr(
        bootstrap, "find_auth_user", lambda *args, **kwargs: _auth_user(["system-users"])
    )
    monkeypatch.setattr(bootstrap, "_login_for_token", lambda *args, **kwargs: "non-admin-token")

    state = bootstrap.ensure_non_admin_user("http://localhost:8124", "admin-token")

    assert state["is_admin"] is False
    assert state["group_ids"] == ["system-users"]
    assert state["token"] == "non-admin-token"
    # The password is not part of the result: no caller needs it and it must
    # not travel into any log channel.
    assert "password" not in state


def test_ensure_non_admin_user_rejects_an_existing_admin(monkeypatch):
    monkeypatch.setattr(
        bootstrap, "find_auth_user", lambda *args, **kwargs: _auth_user(["system-admin"])
    )

    with pytest.raises(bootstrap.BootstrapError, match="admin group"):
        bootstrap.ensure_non_admin_user("http://localhost:8124", "admin-token")


def test_ensure_non_admin_user_rejects_an_unexpected_group(monkeypatch):
    monkeypatch.setattr(
        bootstrap, "find_auth_user", lambda *args, **kwargs: _auth_user(["system-read-only"])
    )

    with pytest.raises(bootstrap.BootstrapError, match="not in group"):
        bootstrap.ensure_non_admin_user("http://localhost:8124", "admin-token")

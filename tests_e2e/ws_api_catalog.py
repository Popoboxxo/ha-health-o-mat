"""Read the admin-only websocket command catalog straight from `ws_api.py`.

The E2E runner image (`Dockerfile.e2e`) ships the integration sources but has
no Home Assistant package installed, so
`import custom_components.health_o_mat.ws_api` is not available there. Parsing
the module's literal assignments with `ast` keeps `ADMIN_ONLY_COMMANDS` the
single source of truth for the admin-gate tests instead of duplicating the
command names in the test file: a command added to (or removed from) the
catalog automatically changes the parametrization, and the coverage test in
`test_admin_gate_e2e.py` fails when the catalog grows an unhandled entry.

The parser is deliberately narrow — it understands exactly the shape used by
`async_register_ws_api` and raises `CatalogError` instead of guessing when that
shape changes. `tests/test_ws_api.py` guards it against the real module.
"""

from __future__ import annotations

import ast
from pathlib import Path

WS_API_PATH = (
    Path(__file__).resolve().parents[1] / "custom_components" / "health_o_mat" / "ws_api.py"
)


class CatalogError(RuntimeError):
    """`ws_api.py` no longer has the shape this parser expects."""


def _command_constants(tree: ast.Module) -> dict[str, str]:
    """All `COMMAND_* = "health_o_mat/..."` string assignments."""
    constants: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        value = node.value
        if (
            isinstance(target, ast.Name)
            and target.id.startswith("COMMAND_")
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            constants[target.id] = value.value
    return constants


def _admin_only_constant_names(tree: ast.Module) -> list[str]:
    """The constant names inside the `frozenset({...})` of ADMIN_ONLY_COMMANDS."""
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name) or node.target.id != "ADMIN_ONLY_COMMANDS":
            continue
        call = node.value
        if not isinstance(call, ast.Call) or not call.args or not isinstance(call.args[0], ast.Set):
            raise CatalogError("ADMIN_ONLY_COMMANDS is not built from a literal set")
        names: list[str] = []
        for element in call.args[0].elts:
            if not isinstance(element, ast.Name):
                raise CatalogError(f"non-name element in ADMIN_ONLY_COMMANDS: {ast.dump(element)}")
            names.append(element.id)
        return names
    raise CatalogError("ADMIN_ONLY_COMMANDS not found in ws_api.py")


def admin_only_commands(path: Path = WS_API_PATH) -> dict[str, str]:
    """`{constant name: command type}` for every entry in ADMIN_ONLY_COMMANDS.

    Example: `{"COMMAND_GET_SETTINGS": "health_o_mat/get_settings", ...}` —
    membership in that set is what makes `async_register_ws_api` wrap a handler
    in HA's `require_admin`, so the set *is* the gate definition.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants = _command_constants(tree)
    commands: dict[str, str] = {}
    for name in _admin_only_constant_names(tree):
        try:
            commands[name] = constants[name]
        except KeyError as err:
            raise CatalogError(f"{name} is not a string constant in ws_api.py") from err
    return commands

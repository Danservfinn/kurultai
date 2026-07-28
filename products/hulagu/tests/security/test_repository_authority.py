from __future__ import annotations

import ast
import inspect
from pathlib import Path

from hulagu.persistence import identity, repositories
from hulagu.persistence.rls import TenantPrincipal

ROOT = Path(__file__).parents[2]
PERSISTENCE = ROOT / "src" / "hulagu" / "persistence"


def public_methods(module: object) -> list[tuple[str, inspect.Signature]]:
    methods: list[tuple[str, inspect.Signature]] = []
    for _, cls in inspect.getmembers(module, inspect.isclass):
        if cls.__module__ != module.__name__:
            continue
        for name, method in inspect.getmembers(cls, inspect.isfunction):
            if not name.startswith("_"):
                methods.append((f"{cls.__name__}.{name}", inspect.signature(method)))
    return methods


def test_repository_methods_accept_principal_and_never_raw_tenant_uuid() -> None:
    methods = public_methods(repositories)
    assert methods
    for name, signature in methods:
        parameters = list(signature.parameters.values())[1:]
        assert all(parameter.name != "tenant_id" for parameter in parameters), name
        assert any(parameter.annotation is TenantPrincipal or parameter.annotation == "TenantPrincipal" for parameter in parameters), name


def test_identity_surface_is_exactly_three_separated_authority_functions() -> None:
    functions = {name for name, value in inspect.getmembers(identity, inspect.isfunction) if value.__module__ == identity.__name__ and not name.startswith("_")}
    assert functions == {"resolve_enrollment", "promote_consented_enrollment", "resolve_existing_tenant"}


def test_only_db_wrapper_may_emit_raw_app_context_or_expose_execute() -> None:
    violations: list[str] = []
    for path in sorted(PERSISTENCE.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and "SET LOCAL app." in node.value and path.name != "db.py":
                violations.append(f"{path.name}:raw-set")
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in {"execute", "query", "raw_sql"}
                and path.name != "db.py"
            ):
                violations.append(f"{path.name}:{node.name}")
    assert violations == []


def test_repositories_do_not_accept_filesystem_paths_from_callers() -> None:
    for name, signature in public_methods(repositories):
        assert all(parameter.name not in {"path", "storage_path", "filesystem_path"} for parameter in signature.parameters.values()), name

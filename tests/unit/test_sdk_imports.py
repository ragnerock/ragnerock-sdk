"""The package imports only what it declares, and nothing internal.

The SDK is installed on its own — into a notebook, a CI runner, a customer
image — so an import of a library it doesn't declare passes every test in
this repository's environment and fails only once installed elsewhere. This
scan reads the source, so it fails here instead.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = _REPO_ROOT / "ragnerock"

# Top-level modules each declared distribution provides, by normalized name.
_IMPORTS_BY_DISTRIBUTION: dict[str, frozenset[str]] = {
    "azure-identity": frozenset({"azure"}),
    "azure-keyvault-secrets": frozenset({"azure"}),
    "boto3": frozenset({"boto3", "botocore"}),
    "cryptography": frozenset({"cryptography"}),
    "google-cloud-secret-manager": frozenset({"google"}),
    "httpx": frozenset({"httpx"}),
    "pandas": frozenset({"pandas"}),
    "pydantic": frozenset({"pydantic", "pydantic_core"}),
    "pyyaml": frozenset({"yaml"}),
    "rich": frozenset({"rich"}),
    "typer": frozenset({"typer", "click"}),
}

# Internal packages of the Ragnerock platform that must never be imported.
_FORBIDDEN_MODULES = frozenset({"core", "keyring", "sqlalchemy", "sqlmodel"})
_FORBIDDEN_SUBMODULES = (
    "ragnerock.harness",
    "ragnerock.orchestrator",
    "ragnerock.db_models",
    "ragnerock.sealing",
    "ragnerock.sanitize",
    "ragnerock.chat",
    "ragnerock.ingestor",
    "ragnerock.provider",
    "ragnerock.iam",
)

_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _normalize(name: str) -> str:
    """Normalize a distribution name as PEP 503 does."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared_distributions() -> set[str]:
    """Return the normalized names of every dependency and optional dependency."""
    project = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())["project"]
    requirements = list(project["dependencies"])
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    names: set[str] = set()
    for requirement in requirements:
        match = _REQUIREMENT_NAME.match(requirement)
        assert match is not None, f"Unparseable requirement {requirement!r}"
        names.add(_normalize(match.group(1)))
    return names


def _imports(path: Path) -> set[str]:
    """Return every absolutely imported module name in a file (any depth)."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


_SOURCES = sorted(_PACKAGE.rglob("*.py"))


def test_every_distribution_in_the_map_is_declared() -> None:
    assert set(_IMPORTS_BY_DISTRIBUTION) <= _declared_distributions()


@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: str(p.relative_to(_REPO_ROOT)))
def test_imports_only_declared_dependencies(path: Path) -> None:
    allowed = set(sys.stdlib_module_names) | {"ragnerock", "__future__"}
    for modules in _IMPORTS_BY_DISTRIBUTION.values():
        allowed |= modules
    roots = {name.split(".")[0] for name in _imports(path)}
    assert roots <= allowed, f"undeclared imports: {sorted(roots - allowed)}"


@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: str(p.relative_to(_REPO_ROOT)))
def test_imports_nothing_internal(path: Path) -> None:
    names = _imports(path)
    roots = {name.split(".")[0] for name in names}
    assert not roots & _FORBIDDEN_MODULES
    assert not [n for n in names if n.startswith(_FORBIDDEN_SUBMODULES)]


def test_cloud_sdks_are_imported_lazily() -> None:
    """Cloud SDKs are optional extras, so only function-local imports may use them."""
    optional = {"google", "boto3", "botocore", "azure", "pandas"}
    for path in _SOURCES:
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = node.module if isinstance(node, ast.ImportFrom) else None
                names = [module] if module else [a.name for a in node.names]  # type: ignore[union-attr]
                for name in names:
                    if name is not None:
                        assert name.split(".")[0] not in optional, (
                            f"{path.relative_to(_REPO_ROOT)} imports {name} at module level"
                        )

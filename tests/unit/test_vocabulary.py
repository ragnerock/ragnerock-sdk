"""Guard against the retired backend vocabulary in the public SDK surface.

The API renamed workflows to agents, operators to tasks, jobs to runs, document
groups to document folders, sinks to outputs and halts to pauses. This walks
the names a caller can reach — package exports, client sections, their methods
and parameters, model fields and enum members — and fails on the old words.

Each allowlist entry names where the word is allowed and why. A second test
fails on any entry nothing needs, so the list can't go stale.
"""

from __future__ import annotations

import enum
import inspect
import re
import typing
from collections.abc import Iterator

import pydantic
import pytest

import ragnerock
import ragnerock.client
import ragnerock.gitops
from ragnerock.client import RagnerockClient

RETIRED = {
    "workflow",
    "workflows",
    "operator",
    "operators",
    "job",
    "jobs",
    "sink",
    "sinks",
    "halt",
    "halted",
    "group",
    "groups",
    "ungrouped",
}

# (where, name) -> why the retired word is correct there.
ALLOWED: dict[tuple[str, str], str] = {
    ("ragnerock.client", "FilterOperator"): "a comparison operator in document filters",
    ("ragnerock.gitops", "API_GROUP"): "the apiVersion group, ragnerock.com/",
    (
        "param:_RunsSection.create",
        "group_id",
    ): "the client-side batch key, not a folder",
    (
        "field:RunOutputDeliveriesResponse",
        "groups",
    ): "one group of deliveries per output",
    ("ragnerock.client", "OutputDeliveryGroup"): "one group of deliveries per output",
}

_PARTS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


def _words(name: str) -> set[str]:
    return {part.lower() for part in _PARTS.findall(name)}


def _surface() -> Iterator[tuple[str, str]]:
    """Yield (where, name) for every name a caller can reach."""
    for module in (ragnerock, ragnerock.client, ragnerock.gitops):
        for name in module.__all__:
            yield module.__name__, name
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, pydantic.BaseModel):
                for field in obj.model_fields:
                    yield f"field:{name}", field
            elif isinstance(obj, type) and issubclass(obj, enum.Enum):
                for member in obj:
                    yield f"member:{name}", member.name
                    if isinstance(member.value, str):
                        yield f"value:{name}", member.value
    for attr, prop in inspect.getmembers(RagnerockClient):
        if attr.startswith("_") or not isinstance(prop, property):
            continue
        yield "RagnerockClient", attr
        yield from _section(_returns(prop))


def _returns(prop: property) -> object:
    """Resolve a property's return annotation in its defining module."""
    return typing.get_type_hints(prop.fget).get("return")


def _section(section: object) -> Iterator[tuple[str, str]]:
    if not isinstance(section, type):
        return
    for method_name, method in inspect.getmembers(section, inspect.isfunction):
        if method_name.startswith("_"):
            continue
        yield section.__name__, method_name
        for param in inspect.signature(method).parameters:
            if param != "self":
                yield f"param:{section.__name__}.{method_name}", param
    for attr, prop in inspect.getmembers(section):
        if not attr.startswith("_") and isinstance(prop, property):
            yield section.__name__, attr
            yield from _section(_returns(prop))


def test_public_surface_uses_current_vocabulary() -> None:
    offenders = sorted(
        f"{where}: {name}"
        for where, name in set(_surface())
        if _words(name) & RETIRED and (where, name) not in ALLOWED
    )
    assert offenders == [], "retired vocabulary in the public SDK:\n" + "\n".join(
        offenders
    )


@pytest.mark.parametrize("entry", sorted(ALLOWED))
def test_allowlist_entries_are_still_needed(entry: tuple[str, str]) -> None:
    assert entry in set(_surface()), f"stale allowlist entry: {entry}"

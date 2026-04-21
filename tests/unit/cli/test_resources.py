"""Tests for the kind registry."""

from __future__ import annotations

import pytest

from ragnerock.cli.resources import UnknownKindError, all_kinds, resolve_kind


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("doc", "Document"),
        ("docs", "Document"),
        ("Document", "Document"),
        ("DOCUMENT", "Document"),
        ("op", "Operator"),
        ("wf", "Workflow"),
        ("workflows", "Workflow"),
        ("anno", "Annotation"),
        ("grp", "DocumentGroup"),
        ("page", "Page"),
        ("chunk", "Chunk"),
        ("job", "Job"),
    ],
)
def test_resolve_kind_aliases(alias: str, expected: str) -> None:
    spec = resolve_kind(alias)
    assert spec.kind == expected


def test_unknown_kind_raises_with_suggestion() -> None:
    with pytest.raises(UnknownKindError) as excinfo:
        resolve_kind("widget")
    assert "widget" in str(excinfo.value)
    assert "Document" in str(excinfo.value)


def test_all_kinds_covers_every_writable_resource() -> None:
    writable = {s.kind for s in all_kinds() if s.writable}
    assert writable == {
        "Document",
        "DocumentGroup",
        "Operator",
        "Workflow",
        "Annotation",
    }


def test_read_only_kinds_are_not_writable() -> None:
    read_only = {s.kind for s in all_kinds() if not s.writable}
    assert read_only == {"Chunk", "Page", "Job"}

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


def test_name_deletable_kinds() -> None:
    deletable = {s.kind for s in all_kinds() if s.deletable}
    assert deletable == {"Document", "DocumentGroup", "Operator", "Workflow"}

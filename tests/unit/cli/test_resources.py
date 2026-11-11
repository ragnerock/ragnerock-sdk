"""Tests for the kind registry."""

from __future__ import annotations

from collections import Counter

import pytest

from ragnerock.cli.resources import (
    NAME_FIELDS,
    UnknownKindError,
    all_kinds,
    resolve_kind,
)


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("doc", "Document"),
        ("docs", "Document"),
        ("Document", "Document"),
        ("DOCUMENT", "Document"),
        ("task", "Task"),
        ("tasks", "Task"),
        ("agent", "Agent"),
        ("agents", "Agent"),
        ("anno", "Annotation"),
        ("folder", "DocumentFolder"),
        ("folders", "DocumentFolder"),
        ("documentfolder", "DocumentFolder"),
        ("documentfolders", "DocumentFolder"),
        ("document-folder", "DocumentFolder"),
        ("document-folders", "DocumentFolder"),
        ("page", "Page"),
        ("chunk", "Chunk"),
        ("run", "Run"),
        ("runs", "Run"),
        ("artifact", "OutputArtifact"),
        ("artifacts", "OutputArtifact"),
        ("outputartifact", "OutputArtifact"),
        ("outputartifacts", "OutputArtifact"),
        ("output-artifact", "OutputArtifact"),
        ("output-artifacts", "OutputArtifact"),
        ("tool", "Tool"),
        ("tools", "Tool"),
    ],
)
def test_resolve_kind_aliases(alias: str, expected: str) -> None:
    spec = resolve_kind(alias)
    assert spec.kind == expected


@pytest.mark.parametrize(
    "alias",
    [
        "wf",
        "wfs",
        "workflow",
        "workflows",
        "op",
        "ops",
        "operator",
        "operators",
        "job",
        "jobs",
        "grp",
        "group",
        "groups",
        "documentgroup",
        "documentgroups",
        "workflowartifact",
        "workflowartifacts",
        "workflow-artifact",
        "workflow-artifacts",
        "agenttool",
        "agenttools",
        "agent-tool",
        "agent-tools",
    ],
)
def test_pre_rename_aliases_are_gone(alias: str) -> None:
    with pytest.raises(UnknownKindError):
        resolve_kind(alias)


def test_every_kind_name_and_alias_is_unique() -> None:
    """No alias may silently overwrite another kind's entry in the registry."""
    names = [
        name.lower()
        for spec in all_kinds()
        for name in {spec.kind.lower(), *(a.lower() for a in spec.aliases)}
    ]
    duplicates = sorted(n for n, count in Counter(names).items() if count > 1)
    assert duplicates == []


def test_every_name_and_alias_resolves_to_its_own_kind() -> None:
    for spec in all_kinds():
        for name in (spec.kind, *spec.aliases):
            assert resolve_kind(name) is spec, name


def test_unknown_kind_raises_with_suggestion() -> None:
    with pytest.raises(UnknownKindError) as excinfo:
        resolve_kind("widget")
    assert "widget" in str(excinfo.value)
    assert "Document" in str(excinfo.value)


def test_name_deletable_kinds() -> None:
    deletable = {s.kind for s in all_kinds() if s.deletable}
    assert deletable == {"Document", "DocumentFolder", "Task", "Agent"}


@pytest.mark.parametrize(
    "kind,header,field_name",
    [
        ("Document", "FOLDER", "document_folder_id"),
        ("Task", "KIND", "task_kind"),
        ("Annotation", "TASK", "task_name"),
        ("Skill", "TASKS", "task_count"),
        ("OutputArtifact", "AGENT", "agent_name"),
        ("OutputArtifact", "OUTPUT", "output_name"),
    ],
)
def test_renamed_columns(kind: str, header: str, field_name: str) -> None:
    assert (header, field_name) in resolve_kind(kind).list_columns


def test_name_fields_use_task_name() -> None:
    assert "task_name" in NAME_FIELDS
    assert "operator_name" not in NAME_FIELDS

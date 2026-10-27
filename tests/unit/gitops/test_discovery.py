"""Tests for manifest discovery (:mod:`ragnerock.gitops.discovery`)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
import yaml

from ragnerock.errors import GitOpsError
from ragnerock.gitops import ManifestSet, is_ragnerock_document, load_manifests
from tests.unit.gitops.helpers import agent_doc, secret_doc


def _write(path: Path, *docs: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump_all(list(docs)))
    return path


@pytest.mark.parametrize(
    ("doc", "expected"),
    [
        ({"apiVersion": "ragnerock.com/v1alpha1", "kind": "Agent"}, True),
        ({"apiVersion": "apps/v1", "kind": "Deployment"}, False),
        ({"apiVersion": "v1", "kind": "Operator"}, False),
        ({"kind": "Agent"}, False),
        ("a string", False),
        (None, False),
    ],
)
def test_is_ragnerock_document(doc: object, expected: bool) -> None:
    assert is_ragnerock_document(doc) is expected


def test_directory_is_walked_recursively_and_sorted(tmp_path: Path) -> None:
    _write(tmp_path / "b" / "agent.yaml", agent_doc("second"))
    _write(tmp_path / "a.yml", agent_doc("first"))
    found = load_manifests([tmp_path])
    assert [d["metadata"]["name"] for d in found.documents] == ["first", "second"]
    assert found.files == [str(tmp_path / "a.yml"), str(tmp_path / "b" / "agent.yaml")]


def test_non_ragnerock_documents_are_skipped(tmp_path: Path) -> None:
    _write(
        tmp_path / "mixed.yaml",
        agent_doc(),
        {"apiVersion": "apps/v1", "kind": "Deployment"},
        {"name": "ci-config"},
    )
    _write(tmp_path / "ci.yaml", {"on": "push"})
    found = load_manifests([tmp_path])
    assert len(found) == 1
    assert found.skipped == 3
    assert found.files == [str(tmp_path / "mixed.yaml")]


def test_hidden_entries_and_other_suffixes_are_ignored(tmp_path: Path) -> None:
    _write(tmp_path / ".github" / "workflow.yaml", agent_doc("hidden-dir"))
    _write(tmp_path / ".hidden.yaml", agent_doc("hidden-file"))
    (tmp_path / "notes.txt").write_text("apiVersion: ragnerock.com/v1alpha1")
    _write(tmp_path / "visible.yaml", agent_doc("visible"))
    found = load_manifests([tmp_path])
    assert [d["metadata"]["name"] for d in found.documents] == ["visible"]


def test_multiple_sources_merge_in_order(tmp_path: Path) -> None:
    secrets = _write(tmp_path / "secrets.yaml", secret_doc({"stringData": {"a": "v"}}))
    agents = _write(tmp_path / "agents.yaml", agent_doc())
    found = load_manifests([agents, secrets])
    assert found.kinds() == ["Agent", "Secret"]


def test_stdin_source() -> None:
    stream = io.StringIO(yaml.safe_dump_all([agent_doc("from-stdin")]))
    found = load_manifests(["-"], stdin=stream)
    assert found.documents[0]["metadata"]["name"] == "from-stdin"
    assert found.files == ["<stdin>"]


def test_empty_directory_is_an_empty_set(tmp_path: Path) -> None:
    found = load_manifests([tmp_path])
    assert isinstance(found, ManifestSet)
    assert len(found) == 0


def test_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(GitOpsError, match="does not exist"):
        load_manifests([tmp_path / "nope.yaml"])


def test_invalid_yaml_names_the_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("kind: [unclosed")
    with pytest.raises(GitOpsError, match="bad.yaml"):
        load_manifests([bad])

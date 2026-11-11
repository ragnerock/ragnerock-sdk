"""Tests for manifest discovery (:mod:`ragnerock.gitops.discovery`)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
import yaml

from ragnerock.errors import GitOpsError
from ragnerock.gitops import (
    API_VERSION,
    RETIRED_API_VERSIONS,
    ManifestSet,
    is_ragnerock_document,
    load_manifests,
)
from tests.unit.gitops.helpers import secret_doc, task_doc

V1ALPHA1 = "ragnerock.com/v1alpha1"


def _write(path: Path, *docs: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump_all(list(docs)))
    return path


@pytest.mark.parametrize(
    ("doc", "expected"),
    [
        ({"apiVersion": "ragnerock.com/v1alpha2", "kind": "Task"}, True),
        ({"apiVersion": "ragnerock.com/v1alpha1", "kind": "Agent"}, True),
        ({"apiVersion": "apps/v1", "kind": "Deployment"}, False),
        ({"apiVersion": "v1", "kind": "Task"}, False),
        ({"kind": "Task"}, False),
        ("a string", False),
        (None, False),
    ],
)
def test_is_ragnerock_document(doc: object, expected: bool) -> None:
    assert is_ragnerock_document(doc) is expected


def test_directory_is_walked_recursively_and_sorted(tmp_path: Path) -> None:
    _write(tmp_path / "b" / "task.yaml", task_doc("second"))
    _write(tmp_path / "a.yml", task_doc("first"))
    found = load_manifests([tmp_path])
    assert [d["metadata"]["name"] for d in found.documents] == ["first", "second"]
    assert found.files == [str(tmp_path / "a.yml"), str(tmp_path / "b" / "task.yaml")]


def test_non_ragnerock_documents_are_skipped(tmp_path: Path) -> None:
    _write(
        tmp_path / "mixed.yaml",
        task_doc(),
        {"apiVersion": "apps/v1", "kind": "Deployment"},
        {"name": "ci-config"},
    )
    _write(tmp_path / "ci.yaml", {"on": "push"})
    found = load_manifests([tmp_path])
    assert len(found) == 1
    assert found.skipped == 3
    assert found.files == [str(tmp_path / "mixed.yaml")]


def test_hidden_entries_and_other_suffixes_are_ignored(tmp_path: Path) -> None:
    _write(tmp_path / ".github" / "workflow.yaml", task_doc("hidden-dir"))
    _write(tmp_path / ".hidden.yaml", task_doc("hidden-file"))
    (tmp_path / "notes.txt").write_text(f"apiVersion: {API_VERSION}")
    _write(tmp_path / "visible.yaml", task_doc("visible"))
    found = load_manifests([tmp_path])
    assert [d["metadata"]["name"] for d in found.documents] == ["visible"]


def test_multiple_sources_merge_in_order(tmp_path: Path) -> None:
    secrets = _write(tmp_path / "secrets.yaml", secret_doc({"stringData": {"a": "v"}}))
    tasks = _write(tmp_path / "tasks.yaml", task_doc())
    found = load_manifests([tasks, secrets])
    assert found.kinds() == ["Task", "Secret"]


def test_stdin_source() -> None:
    stream = io.StringIO(yaml.safe_dump_all([task_doc("from-stdin")]))
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


# -- apiVersion ------------------------------------------------------------------


def test_current_api_version_constants() -> None:
    assert API_VERSION == "ragnerock.com/v1alpha2"
    assert V1ALPHA1 in RETIRED_API_VERSIONS
    assert API_VERSION not in RETIRED_API_VERSIONS


def test_v1alpha1_is_refused_with_source_and_index(tmp_path: Path) -> None:
    old = {**task_doc(), "apiVersion": V1ALPHA1, "kind": "Agent"}
    path = _write(
        tmp_path / "tasks.yaml",
        task_doc("current"),
        {"apiVersion": "apps/v1", "kind": "Deployment"},
        old,
    )
    with pytest.raises(GitOpsError) as excinfo:
        load_manifests([path])
    err = excinfo.value
    assert err.message == (
        f"{path}: document[2]: This manifest uses apiVersion v1alpha1; "
        "export it again from Ragnerock to get v1alpha2."
    )
    assert err.suggestion is not None
    assert "a `Task` is what v1alpha1 called an `Agent`" in err.suggestion
    assert "an `Agent` is what it called a `Workflow`" in err.suggestion
    assert "Migrating to 3.0" in str(err)


def test_v1alpha1_in_any_file_refuses_the_whole_set(tmp_path: Path) -> None:
    _write(tmp_path / "a.yaml", task_doc())
    _write(
        tmp_path / "b.yaml",
        {**secret_doc({"stringData": {"a": "v"}}), "apiVersion": V1ALPHA1},
    )
    with pytest.raises(GitOpsError, match=r"b\.yaml: document\[0\]: .*v1alpha1"):
        load_manifests([tmp_path])


def test_v1alpha1_on_stdin_names_stdin() -> None:
    stream = io.StringIO(yaml.safe_dump({**task_doc(), "apiVersion": V1ALPHA1}))
    with pytest.raises(GitOpsError, match=r"<stdin>: document\[0\]"):
        load_manifests(["-"], stdin=stream)


def test_other_versions_are_left_to_the_server(tmp_path: Path) -> None:
    future = {**task_doc(), "apiVersion": "ragnerock.com/v1beta1"}
    found = load_manifests([_write(tmp_path / "future.yaml", future)])
    assert found.documents == [future]


def test_retired_version_outside_the_group_is_just_skipped(tmp_path: Path) -> None:
    found = load_manifests(
        [_write(tmp_path / "other.yaml", {"apiVersion": "v1alpha1", "kind": "Agent"})]
    )
    assert len(found) == 0
    assert found.skipped == 1

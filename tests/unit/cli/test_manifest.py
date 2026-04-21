"""Tests for manifest loading, validation, and apply-order sorting."""

from __future__ import annotations

import io
import textwrap
from pathlib import Path

import pytest

from ragnerock.cli.manifest import (
    ManifestError,
    read_manifests,
    sort_by_apply_order,
)


def _write(tmp_path: Path, name: str, body: str) -> str:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body).lstrip())
    return str(path)


def test_reads_single_file(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "op.yaml",
        """
        kind: Operator
        metadata:
          name: sentiment
        spec:
          generation_prompt: "x"
        """,
    )
    docs = read_manifests([path])
    assert len(docs) == 1
    assert docs[0].spec_kind.kind == "Operator"
    assert docs[0].name == "sentiment"


def test_multi_doc_file(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "multi.yaml",
        """
        kind: Operator
        metadata: { name: op-a }
        spec: {}
        ---
        kind: Operator
        metadata: { name: op-b }
        spec: {}
        """,
    )
    docs = read_manifests([path])
    assert [d.name for d in docs] == ["op-a", "op-b"]


def test_stdin_dash(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO(
        textwrap.dedent(
            """
            kind: Operator
            metadata: { name: from-stdin }
            spec: {}
            """
        ).lstrip()
    )
    monkeypatch.setattr("sys.stdin", stream)
    docs = read_manifests(["-"])
    assert docs[0].source == "<stdin>"
    assert docs[0].name == "from-stdin"


def test_empty_sources_raises() -> None:
    with pytest.raises(ManifestError):
        read_manifests([])


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ManifestError):
        read_manifests([str(tmp_path / "nope.yaml")])


def test_missing_kind_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "bad.yaml",
        """
        metadata: { name: x }
        spec: {}
        """,
    )
    with pytest.raises(ManifestError, match="kind"):
        read_manifests([path])


def test_unknown_kind_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "bad.yaml",
        """
        kind: Widget
        metadata: { name: x }
        spec: {}
        """,
    )
    with pytest.raises(ManifestError, match="Unknown resource kind"):
        read_manifests([path])


def test_read_only_kind_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "bad.yaml",
        """
        kind: Chunk
        metadata: { name: x }
        spec: {}
        """,
    )
    with pytest.raises(ManifestError, match="read-only"):
        read_manifests([path])


def test_missing_metadata_name_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "bad.yaml",
        """
        kind: Operator
        metadata: {}
        spec: {}
        """,
    )
    with pytest.raises(ManifestError, match="metadata.name"):
        read_manifests([path])


def test_api_version_defaults_to_v1(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "op.yaml",
        """
        kind: Operator
        metadata: { name: op }
        spec: {}
        """,
    )
    docs = read_manifests([path])
    assert docs[0].api_version == "v1"


def test_api_version_explicit_v1_accepted(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "op.yaml",
        """
        apiVersion: v1
        kind: Operator
        metadata: { name: op }
        spec: {}
        """,
    )
    docs = read_manifests([path])
    assert docs[0].api_version == "v1"


def test_unsupported_api_version_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "bad.yaml",
        """
        apiVersion: v2
        kind: Operator
        metadata: { name: op }
        spec: {}
        """,
    )
    with pytest.raises(ManifestError, match="unsupported apiVersion"):
        read_manifests([path])


def test_non_string_api_version_raises(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "bad.yaml",
        """
        apiVersion: 1
        kind: Operator
        metadata: { name: op }
        spec: {}
        """,
    )
    with pytest.raises(ManifestError, match="apiVersion"):
        read_manifests([path])


_SIMPLE_OP = """
kind: Operator
metadata:
  name: {name}
spec: {{}}
"""


def _write_op(tmp_path: Path, rel: str, op_name: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(_SIMPLE_OP.format(name=op_name)).lstrip())
    return path


def test_directory_source_loads_all_yaml_files(tmp_path: Path) -> None:
    _write_op(tmp_path, "a.yaml", "op-a")
    _write_op(tmp_path, "b.yaml", "op-b")
    docs = read_manifests([str(tmp_path)])
    assert sorted(d.name for d in docs) == ["op-a", "op-b"]


def test_directory_source_includes_yml_extension(tmp_path: Path) -> None:
    _write_op(tmp_path, "a.yaml", "op-a")
    _write_op(tmp_path, "b.yml", "op-b")
    docs = read_manifests([str(tmp_path)])
    assert sorted(d.name for d in docs) == ["op-a", "op-b"]


def test_directory_source_is_case_insensitive(tmp_path: Path) -> None:
    _write_op(tmp_path, "upper.YAML", "op-upper")
    docs = read_manifests([str(tmp_path)])
    assert [d.name for d in docs] == ["op-upper"]


def test_directory_source_recurses_into_subdirectories(tmp_path: Path) -> None:
    _write_op(tmp_path, "top.yaml", "op-top")
    _write_op(tmp_path, "sub/nested.yaml", "op-nested")
    docs = read_manifests([str(tmp_path)])
    assert sorted(d.name for d in docs) == ["op-nested", "op-top"]


def test_directory_source_skips_non_yaml_files(tmp_path: Path) -> None:
    _write_op(tmp_path, "op.yaml", "op-only")
    (tmp_path / "README.md").write_text("docs")
    (tmp_path / "notes.txt").write_text("hi")
    docs = read_manifests([str(tmp_path)])
    assert [d.name for d in docs] == ["op-only"]


def test_directory_source_skips_hidden_files(tmp_path: Path) -> None:
    _write_op(tmp_path, "visible.yaml", "op-visible")
    _write_op(tmp_path, ".hidden.yaml", "op-hidden")
    docs = read_manifests([str(tmp_path)])
    assert [d.name for d in docs] == ["op-visible"]


def test_directory_source_skips_hidden_subdirectories(tmp_path: Path) -> None:
    _write_op(tmp_path, "top.yaml", "op-top")
    _write_op(tmp_path, ".git/config.yaml", "op-hidden-dir")
    docs = read_manifests([str(tmp_path)])
    assert [d.name for d in docs] == ["op-top"]


def test_directory_source_sorted_deterministically(tmp_path: Path) -> None:
    _write_op(tmp_path, "b.yaml", "op-b")
    _write_op(tmp_path, "a.yaml", "op-a")
    docs = read_manifests([str(tmp_path)])
    assert [d.name for d in docs] == ["op-a", "op-b"]


def test_directory_source_empty_raises(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="No YAML manifests"):
        read_manifests([str(tmp_path)])


def test_directory_source_only_non_yaml_files_raises(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("docs")
    with pytest.raises(ManifestError, match="No YAML manifests"):
        read_manifests([str(tmp_path)])


def test_mixed_file_and_directory_sources(tmp_path: Path) -> None:
    file_path = _write_op(tmp_path, "standalone.yaml", "op-standalone")
    dir_path = tmp_path / "dir"
    _write_op(dir_path, "inside.yaml", "op-inside")
    docs = read_manifests([str(file_path), str(dir_path)])
    assert [d.name for d in docs] == ["op-standalone", "op-inside"]


def test_directory_source_with_invalid_yaml_file_raises(tmp_path: Path) -> None:
    _write_op(tmp_path, "good.yaml", "op-good")
    (tmp_path / "bad.yaml").write_text("kind: Operator\nmetadata: { name: x\n")
    with pytest.raises(ManifestError, match="Invalid YAML"):
        read_manifests([str(tmp_path)])


def test_apply_order_sort_places_operators_before_workflows(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "mixed.yaml",
        """
        kind: Workflow
        metadata: { name: w }
        spec: {}
        ---
        kind: Operator
        metadata: { name: o }
        spec: {}
        ---
        kind: DocumentGroup
        metadata: { name: g }
        spec: {}
        ---
        kind: Document
        metadata: { name: d }
        spec: { file_path: ./a.pdf }
        """,
    )
    docs = read_manifests([path])
    ordered = sort_by_apply_order(docs)
    assert [d.spec_kind.kind for d in ordered] == [
        "DocumentGroup",
        "Operator",
        "Document",
        "Workflow",
    ]

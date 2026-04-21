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

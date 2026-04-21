"""Tests for resource model behavior: construction, enums, binding."""

from __future__ import annotations

import pytest

from ragnerock import (
    Annotation,
    Chunk,
    ChunkType,
    Document,
    DocumentGroup,
    FileType,
    Job,
    JobStatus,
    JobType,
    Operator,
    Page,
    Workflow,
    WorkflowNode,
)


class TestDefaults:
    """Fresh resources have their identity fields unset."""

    @pytest.mark.parametrize(
        "cls",
        [Document, DocumentGroup, Chunk, Page, Operator, Workflow, Job],
    )
    def test_fresh_resource_has_no_id(self, cls):
        assert cls().id is None

    def test_fresh_annotation_has_no_root_id(self):
        ann = Annotation()
        assert ann.root_id is None
        assert ann.id is None  # proxies to root_id


class TestEnums:
    """Resource enums are ``IntEnum`` — integer-compatible but typed."""

    def test_file_type_values_are_ints(self):
        assert int(FileType.PDF) == 3
        assert FileType.PDF == 3

    def test_chunk_type_values(self):
        assert ChunkType.DOCUMENT == 1
        assert ChunkType.PARAGRAPH == 4

    def test_job_status_has_terminal_values(self):
        assert JobStatus.SUCCEEDED == 3
        assert JobStatus.FAILED == 4

    def test_job_type_exists(self):
        assert JobType.MANUAL in JobType


class TestPydanticCoercion:
    """Pydantic coerces UUID strings / integer enum values as expected."""

    def test_document_accepts_string_ids(self):
        d = Document(
            id="00000000-0000-0000-0000-000000000101",
            project_id="00000000-0000-0000-0000-000000000001",
        )
        # Pydantic converts to UUID
        assert str(d.id).startswith("00000000")

    def test_chunk_type_coerced_from_int(self):
        c = Chunk(document_id="00000000-0000-0000-0000-000000000101", chunk_type=4)
        assert c.chunk_type == ChunkType.PARAGRAPH


class TestBinding:
    """``_bind`` is internal, but the ``_is_bound`` flag is the observable contract."""

    def test_resource_unbound_by_default(self):
        assert not Document()._is_bound

    def test_unbound_resource_list_raises(self):
        doc = Document()
        with pytest.raises(RuntimeError):
            doc.list(Chunk).all()

    def test_bound_resource_is_bound(self, session):
        d = Document()
        session._bind(d)
        assert d._is_bound


class TestAnnotationIdAlias:
    """Annotation's ``id`` property proxies to ``root_id``."""

    def test_id_returns_root_id(self):
        root = "00000000-0000-0000-0000-000000000501"
        ann = Annotation(root_id=root)
        assert str(ann.id) == root


class TestWorkflowNodeDefaults:
    def test_node_has_empty_in_out_lists(self):
        node = WorkflowNode()
        assert node.in_nodes == []
        assert node.out_nodes == []
        assert node.persist is True
        assert node.on_error == "FAIL_JOB"

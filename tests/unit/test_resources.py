"""Tests for resource model behavior: construction, enums, binding."""

from __future__ import annotations

import pytest

import ragnerock
from ragnerock import (
    Agent,
    AgentNode,
    Annotation,
    Chunk,
    ChunkType,
    Document,
    DocumentFolder,
    FileType,
    Page,
    Run,
    RunKind,
    RunStatus,
    Task,
    TaskKind,
)


class TestDefaults:
    """Fresh resources have their identity fields unset."""

    @pytest.mark.parametrize(
        "cls",
        [Document, DocumentFolder, Chunk, Page, Task, Agent, Run],
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

    def test_chunk_type_values_match_server(self):
        assert ChunkType.DOCUMENT == 0
        assert ChunkType.PAGE == 1
        assert ChunkType.PARAGRAPH == 2
        assert ChunkType.SENTENCE == 3
        assert ChunkType.ROW == 4
        assert ChunkType.ROW_WINDOW == 5
        assert ChunkType.SHEET == 6

    def test_only_tabular_scopes_accept_input_columns(self):
        assert ChunkType.ROW.accepts_input_columns
        assert ChunkType.SHEET.accepts_input_columns
        assert not ChunkType.PARAGRAPH.accepts_input_columns

    def test_run_status_has_terminal_values(self):
        assert RunStatus.SUCCEEDED == 3
        assert RunStatus.FAILED == 4

    def test_run_kind_values_match_server(self):
        assert RunKind.AUTOMATIC == 1
        assert RunKind.MANUAL == 2

    def test_task_kind_values(self):
        assert {k.value for k in TaskKind} == {"LLM", "CODE", "MANUAL", "OUTPUT"}


class TestRenamedExports:
    """3.0 is a clean break: the pre-rename names are not exported."""

    @pytest.mark.parametrize(
        "name",
        [
            "DocumentGroup",
            "Job",
            "JobStatus",
            "JobType",
            "Operator",
            "OperatorKind",
            "Workflow",
            "WorkflowNode",
            "WorkflowSchedule",
        ],
    )
    def test_old_name_is_gone(self, name):
        assert not hasattr(ragnerock, name)
        assert name not in ragnerock.__all__


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
        c = Chunk(document_id="00000000-0000-0000-0000-000000000101", chunk_type=2)
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


class TestAgentNodeDefaults:
    def test_node_has_empty_in_out_lists(self):
        node = AgentNode()
        assert node.in_nodes == []
        assert node.out_nodes == []
        assert node.persist is True
        assert node.on_error == "SKIP_NODE"
        assert node.target_input_id is None
        assert node.context_input_ids == []

    def test_agent_has_inputs_and_outputs(self):
        agent = Agent()
        assert agent.inputs == []
        assert agent.outputs == []
        assert "resources" not in Agent.model_fields
        assert "sinks" not in Agent.model_fields

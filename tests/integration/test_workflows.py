"""End-to-end Workflow flows.

CRUD is always exercised. The actual ``run()`` test is opt-in (gated on
``RAGNEROCK_ITEST_RUN_WORKFLOWS``) because it consumes LLM quota and can take
minutes to complete.
"""

from __future__ import annotations

from uuid import uuid4

from ragnerock import (
    ChunkType,
    Document,
    Job,
    JobStatus,
    Operator,
    Workflow,
    WorkflowNode,
)

from tests.integration.conftest import skip_unless_env


def _make_noop_operator(name: str) -> Operator:
    return Operator(
        name=name,
        description="noop operator for wiring tests",
        jsonschema={"type": "object", "properties": {"value": {"type": "string"}}},
        generation_prompt='Return {"value": "hello"}.',
        chunk_type=ChunkType.DOCUMENT,
    )


class TestCrud:
    def test_workflow_crud(self, session, unique_name):
        wf = Workflow(
            name=unique_name,
            description="SDK integration test workflow",
            auto_run_on_upload=False,
        )
        session.add(wf)
        session.commit()
        assert wf.id is not None

        try:
            fetched = session.get(Workflow, id=wf.id)
            assert fetched is not None
            assert fetched.name == unique_name

            by_name = session.get(Workflow, name=unique_name)
            assert by_name is not None
            assert by_name.id == wf.id

            names = [w.name for w in session.list(Workflow)]
            assert unique_name in names

            new_description = "Updated by integration test"
            wf.description = new_description
            session.update(wf)
            session.commit()
            session.refresh(wf)
            assert wf.description == new_description
        finally:
            session.delete(wf)
            session.commit()

        assert session.get(Workflow, id=wf.id) is None

    def test_get_by_missing_name_returns_none(self, session):
        assert session.get(Workflow, name=f"sdk-itest-no-wf-{uuid4().hex[:8]}") is None


class TestNodeWiring:
    """End-to-end exercise of `wf.add_node(...)` + `>>` wiring."""

    def test_add_nodes_and_wire(self, session, unique_name):
        op_a = _make_noop_operator(f"{unique_name}-a")
        op_b = _make_noop_operator(f"{unique_name}-b")
        op_c = _make_noop_operator(f"{unique_name}-c")
        session.add(op_a)
        session.add(op_b)
        session.add(op_c)
        session.commit()

        wf = Workflow(name=unique_name, auto_run_on_upload=False)
        session.add(wf)
        session.commit()

        try:
            a = wf.add_node(operator=op_a)
            b = wf.add_node(operator=op_b)
            c = wf.add_node(operator=op_c)
            session.commit()
            assert a.id is not None
            assert b.id is not None
            assert c.id is not None

            # Wire: [a, b] >> c
            [a, b] >> c
            session.commit()

            fetched = session.get(Workflow, id=wf.id)
            assert fetched is not None
            nodes_by_id = {n.id: n for n in fetched.nodes}
            assert c.id in nodes_by_id[a.id].out_nodes
            assert c.id in nodes_by_id[b.id].out_nodes
            assert set(nodes_by_id[c.id].in_nodes) == {a.id, b.id}
        finally:
            session.delete(wf)
            session.commit()
            for op in (op_a, op_b, op_c):
                session.delete(op)
            session.commit()


class TestGetNode:
    """End-to-end coverage of ``session.get(WorkflowNode, ...)``."""

    def test_get_by_node_id_and_workflow_id(self, session, unique_name):
        op = _make_noop_operator(unique_name)
        session.add(op)
        session.commit()

        wf = Workflow(name=unique_name, auto_run_on_upload=False)
        session.add(wf)
        session.commit()

        try:
            node = wf.add_node(operator=op)
            session.commit()
            assert node.id is not None

            fetched = session.get(WorkflowNode, id=node.id, workflow_id=wf.id)
            assert fetched is not None
            assert fetched.id == node.id
            assert fetched.operator_id == op.id
            assert fetched.operator_name == unique_name
        finally:
            session.delete(wf)
            session.commit()
            session.delete(op)
            session.commit()

    def test_get_by_workflow_name_and_operator_name(self, session, unique_name):
        op = _make_noop_operator(unique_name)
        session.add(op)
        session.commit()

        wf = Workflow(name=unique_name, auto_run_on_upload=False)
        session.add(wf)
        session.commit()

        try:
            node = wf.add_node(operator=op)
            session.commit()
            assert node.id is not None

            fetched = session.get(
                WorkflowNode, name=unique_name, workflow_name=unique_name
            )
            assert fetched is not None
            assert fetched.id == node.id
        finally:
            session.delete(wf)
            session.commit()
            session.delete(op)
            session.commit()

    def test_missing_node_returns_none(self, session, unique_name):
        wf = Workflow(name=unique_name, auto_run_on_upload=False)
        session.add(wf)
        session.commit()

        try:
            assert (
                session.get(
                    WorkflowNode,
                    id=uuid4(),
                    workflow_id=wf.id,
                )
                is None
            )
        finally:
            session.delete(wf)
            session.commit()

    def test_missing_workflow_returns_none(self, session):
        assert (
            session.get(
                WorkflowNode,
                id=uuid4(),
                workflow_name=f"sdk-itest-no-wf-{uuid4().hex[:8]}",
            )
            is None
        )


@skip_unless_env("RAGNEROCK_ITEST_RUN_WORKFLOWS")
def test_run_and_wait(session, unique_name, tmp_path):
    """End-to-end: upload doc, create operator + workflow, run, wait, assert done.

    Opt-in only — consumes LLM quota.
    """
    op = Operator(
        name=unique_name,
        description="noop operator",
        jsonschema={"type": "object", "properties": {"value": {"type": "string"}}},
        generation_prompt='Return {"value": "hello"}.',
        chunk_type=ChunkType.DOCUMENT,
    )
    session.add(op)
    session.commit()

    wf = Workflow(name=unique_name, auto_run_on_upload=False)
    session.add(wf)
    session.commit()

    file_path = tmp_path / f"{unique_name}.txt"
    file_path.write_text("Hello world.")
    doc = Document(file_path=str(file_path), name=unique_name)
    session.add(doc)
    session.commit()

    try:
        job = session.run(wf, documents=[doc])
        assert isinstance(job, Job)
        assert job.id is not None
        job.wait(timeout=300, poll_interval=5)
        assert job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED)
    finally:
        session.delete(doc)
        session.commit()
        session.delete(wf)
        session.commit()
        session.delete(op)
        session.commit()

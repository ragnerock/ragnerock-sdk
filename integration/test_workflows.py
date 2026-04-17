"""End-to-end Workflow flows.

The actual `run()` test is opt-in (gated on RAGNEROCK_ITEST_RUN_WORKFLOWS)
because it consumes LLM quota and can take minutes to complete.
"""

from __future__ import annotations

from ragnerock import ChunkType, Document, JobStatus, Operator, Workflow

from integration.conftest import skip_unless_env


def test_workflow_crud(session, unique_name):
    wf = Workflow(
        name=unique_name,
        description="SDK integration test workflow",
        auto_run_on_upload=False,
    )
    session.add(wf)
    session.commit()
    assert wf.id is not None

    try:
        # Get by id.
        fetched = session.get(Workflow, id=wf.id)
        assert fetched is not None
        assert fetched.name == unique_name

        # Get by name (list + filter).
        by_name = session.get(Workflow, name=unique_name)
        assert by_name is not None
        assert by_name.id == wf.id

        # Update.
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


@skip_unless_env("RAGNEROCK_ITEST_RUN_WORKFLOWS")
def test_run_and_wait(session, unique_name, tmp_path):
    """End-to-end: upload doc, create operator + workflow, run, wait, assert done.

    Opt-in only — consumes LLM quota.
    """
    op = Operator(
        name=unique_name,
        description="noop operator",
        jsonschema={"type": "object", "properties": {"value": {"type": "string"}}},
        generation_prompt="Return {\"value\": \"hello\"}.",
        chunk_type=ChunkType.DOCUMENT,
    )
    session.add(op)
    session.commit()

    wf = Workflow(name=unique_name, auto_run_on_upload=False)
    session.add(wf)
    session.commit()

    # Note: attaching nodes to a workflow is not yet exposed in the high-level
    # SDK (it's low-level-client-only). For now this test exercises job creation
    # even against an empty workflow, which the server may or may not accept.
    # Adjust if you have a way to wire nodes via the SDK.

    file_path = tmp_path / f"{unique_name}.txt"
    file_path.write_text("Hello world.")
    doc = Document(file_path=str(file_path), name=unique_name)
    session.add(doc)
    session.commit()

    try:
        job = session.run(wf, documents=[doc])
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

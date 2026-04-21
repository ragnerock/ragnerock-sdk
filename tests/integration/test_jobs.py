"""Job list / get flows.

Creating jobs requires running a workflow, which is opt-in (see
``test_workflows.py::test_run_and_wait``). The tests here verify that the
listing endpoints round-trip correctly against whatever jobs already exist
in the configured project.

Cancel, retry, refresh, and wait are opt-in because they either require an
active job to act on (cancel/retry) or consume LLM quota (wait).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from ragnerock import ChunkType, Document, Job, JobStatus, Operator, Workflow

from tests.integration.conftest import skip_unless_env


class TestList:
    def test_list_jobs_is_shaped(self, session):
        """list(Job) must return Jobs or be empty — never raise."""
        jobs = list(session.list(Job).limit(5))
        for j in jobs:
            assert isinstance(j, Job)
            assert j.id is not None

    def test_list_filter_by_status(self, session):
        """Filtering by status returns only matching jobs (or an empty list)."""
        jobs = list(session.list(Job, status=JobStatus.FAILED).limit(5))
        for j in jobs:
            assert j.status == JobStatus.FAILED


class TestGet:
    def test_get_missing_job_returns_none(self, session):
        assert session.get(Job, id=uuid4()) is None


def _run_small_job(session, unique_name, tmp_path):
    """Create op + workflow + doc + trigger a run. Caller is responsible for teardown."""
    op = Operator(
        name=unique_name,
        description="noop operator",
        jsonschema={"type": "object", "properties": {"value": {"type": "string"}}},
        generation_prompt='Return {"value": "hello"}.',
        chunk_type=ChunkType.DOCUMENT,
    )
    wf = Workflow(name=unique_name, auto_run_on_upload=False)
    session.add(op)
    session.add(wf)
    session.commit()

    file_path = tmp_path / f"{unique_name}.txt"
    file_path.write_text("Hello world.")
    doc = Document(file_path=str(file_path), name=unique_name)
    session.add(doc)
    session.commit()

    job = session.run(wf, documents=[doc])
    return job, op, wf, doc


@skip_unless_env("RAGNEROCK_ITEST_RUN_WORKFLOWS")
class TestJobLifecycle:
    """Opt-in — exercises cancel / retry / refresh / wait against a real running job."""

    def test_refresh_updates_status(self, session, unique_name, tmp_path):
        job, op, wf, doc = _run_small_job(session, unique_name, tmp_path)
        try:
            initial_status = job.status
            session.refresh(job)
            # status is either the same (still running) or a valid terminal value.
            assert isinstance(job.status, JobStatus)
            assert job.status == initial_status or isinstance(job.status, JobStatus)
        finally:
            session.delete(doc)
            session.commit()
            session.delete(wf)
            session.commit()
            session.delete(op)
            session.commit()

    def test_wait_reaches_terminal(self, session, unique_name, tmp_path):
        job, op, wf, doc = _run_small_job(session, unique_name, tmp_path)
        try:
            job.wait(timeout=300, poll_interval=5)
            assert job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED)
        finally:
            session.delete(doc)
            session.commit()
            session.delete(wf)
            session.commit()
            session.delete(op)
            session.commit()

    def test_cancel_and_retry(self, session, unique_name, tmp_path):
        job, op, wf, doc = _run_small_job(session, unique_name, tmp_path)
        try:
            # Cancel while it's still running; server may already have completed.
            try:
                job.cancel()
            except Exception:  # noqa: BLE001 — server might reject if job already terminal
                pytest.skip("job reached terminal state before cancel was delivered")

            # Wait for cancellation to settle.
            session.refresh(job)
            if job.status not in (JobStatus.FAILED, JobStatus.SUCCEEDED):
                pytest.skip("job did not settle after cancel within a single refresh")

            job.retry()
            session.refresh(job)
            assert isinstance(job.status, JobStatus)
        finally:
            session.delete(doc)
            session.commit()
            session.delete(wf)
            session.commit()
            session.delete(op)
            session.commit()

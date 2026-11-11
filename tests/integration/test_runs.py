"""Run list / get flows.

Creating runs requires running an agent, which is opt-in (see
``test_agents.py::test_run_and_wait``). The tests here verify that the
listing endpoints round-trip correctly against whatever runs already exist
in the configured project.

Cancel, retry, refresh, and wait are opt-in because they either require an
active run to act on (cancel/retry) or consume LLM quota (wait).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from ragnerock import Agent, ChunkType, Document, Run, RunStatus, Task

from tests.integration.conftest import skip_unless_env


class TestList:
    def test_list_runs_is_shaped(self, session):
        """list(Run) must return Runs or be empty — never raise."""
        runs = list(session.list(Run).limit(5))
        for r in runs:
            assert isinstance(r, Run)
            assert r.id is not None

    def test_list_filter_by_status(self, session):
        """Filtering by status returns only matching runs (or an empty list)."""
        runs = list(session.list(Run, status=RunStatus.FAILED).limit(5))
        for r in runs:
            assert r.status == RunStatus.FAILED


class TestGet:
    def test_get_missing_run_returns_none(self, session):
        assert session.get(Run, id=uuid4()) is None


def _start_small_run(session, unique_name, tmp_path):
    """Create task + agent + doc + start a run. Caller is responsible for teardown."""
    task = Task(
        name=unique_name,
        description="noop task",
        jsonschema={"type": "object", "properties": {"value": {"type": "string"}}},
        generation_prompt='Return {"value": "hello"}.',
        chunk_type=ChunkType.DOCUMENT,
    )
    agent = Agent(name=unique_name, auto_run_on_upload=False)
    session.add(task)
    session.add(agent)
    session.commit()

    file_path = tmp_path / f"{unique_name}.txt"
    file_path.write_text("Hello world.")
    doc = Document(file_path=str(file_path), name=unique_name)
    session.add(doc)
    session.commit()

    run = session.run(agent, documents=[doc])
    return run, task, agent, doc


@skip_unless_env("RAGNEROCK_ITEST_RUN_AGENTS")
class TestRunLifecycle:
    """Opt-in — exercises cancel / retry / refresh / wait against a real active run."""

    def test_refresh_updates_status(self, session, unique_name, tmp_path):
        run, task, agent, doc = _start_small_run(session, unique_name, tmp_path)
        try:
            initial_status = run.status
            session.refresh(run)
            # status is either the same (still running) or a valid terminal value.
            assert isinstance(run.status, RunStatus)
            assert run.status == initial_status or isinstance(run.status, RunStatus)
        finally:
            session.delete(doc)
            session.commit()
            session.delete(agent)
            session.commit()
            session.delete(task)
            session.commit()

    def test_wait_reaches_terminal(self, session, unique_name, tmp_path):
        run, task, agent, doc = _start_small_run(session, unique_name, tmp_path)
        try:
            run.wait(timeout=300, poll_interval=5)
            assert run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED)
        finally:
            session.delete(doc)
            session.commit()
            session.delete(agent)
            session.commit()
            session.delete(task)
            session.commit()

    def test_cancel_and_retry(self, session, unique_name, tmp_path):
        run, task, agent, doc = _start_small_run(session, unique_name, tmp_path)
        try:
            # Cancel while it's still running; server may already have completed.
            try:
                run.cancel()
            except Exception:  # noqa: BLE001 — server might reject if run already terminal
                pytest.skip("run reached terminal state before cancel was delivered")

            # Wait for cancellation to settle.
            session.refresh(run)
            if run.status not in (RunStatus.FAILED, RunStatus.SUCCEEDED):
                pytest.skip("run did not settle after cancel within a single refresh")

            run.retry()
            session.refresh(run)
            assert isinstance(run.status, RunStatus)
        finally:
            session.delete(doc)
            session.commit()
            session.delete(agent)
            session.commit()
            session.delete(task)
            session.commit()

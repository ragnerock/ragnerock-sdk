"""Job list / get flows.

Does not create jobs (that's covered by test_workflows.py::test_run_and_wait
behind the opt-in flag). These tests just verify the list / get / stream-shape
endpoints round-trip correctly against the project.
"""

from __future__ import annotations

from ragnerock import Job


def test_list_jobs_is_shaped(session):
    """Calling list(Job) must return an iterator that yields Job instances or is empty."""
    jobs = list(session.list(Job).limit(5))
    for j in jobs:
        assert isinstance(j, Job)
        assert j.id is not None


def test_get_missing_job_returns_none(session):
    from uuid import uuid4

    assert session.get(Job, id=uuid4()) is None

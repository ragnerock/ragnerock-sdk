"""Tests for Job listing, status polling, cancel, retry."""

from __future__ import annotations

import re
from uuid import UUID

from ragnerock import Job, JobStatus
from tests.conftest import TEST_HOST


class TestList:
    def test_list_jobs(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/jobs/\?.*"),
            json=payloads.list_envelope("jobs", [payloads.job()]),
        )
        jobs = session.list(Job).all()
        assert len(jobs) == 1
        assert jobs[0].status == JobStatus.IN_PROGRESS

    def test_list_filter_by_status(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/jobs/\?.*status_filter=.*"),
            json=payloads.list_envelope(
                "jobs", [payloads.job(status=4)]  # FAILED
            ),
        )
        jobs = session.list(Job, status=JobStatus.FAILED).all()
        assert all(j.status == JobStatus.FAILED for j in jobs)


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        jid = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/jobs/{jid}",
            json=payloads.job(id=jid),
        )
        j = session.get(Job, id=jid)
        assert j is not None
        assert j.id == UUID(jid)


class TestRefresh:
    def test_refresh_updates_status(self, httpx_mock, session, payloads):
        jid = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/jobs/{jid}",
            json=payloads.job(id=jid, status=3),  # SUCCEEDED
        )
        j = Job(**payloads.job(id=jid, status=2))
        session._bind(j)
        session.refresh(j)
        assert j.status == JobStatus.SUCCEEDED


class TestCancel:
    def test_cancel_posts(self, httpx_mock, session, payloads):
        jid = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/jobs/{jid}/cancel",
            json={"job_id": jid, "status": "cancelled"},
        )
        j = Job(**payloads.job(id=jid))
        session._bind(j)
        j.cancel()


class TestRetry:
    def test_retry_posts(self, httpx_mock, session, payloads):
        jid = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/jobs/{jid}/retry",
            json={"job_id": jid, "status": "pending"},
        )
        j = Job(**payloads.job(id=jid, status=4))  # FAILED
        session._bind(j)
        j.retry()


class TestWait:
    def test_wait_polls_until_terminal(self, httpx_mock, session, payloads):
        jid = "00000000-0000-0000-0000-000000000801"
        # First two polls return IN_PROGRESS, third returns SUCCEEDED.
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/jobs/{jid}",
            json=payloads.job(id=jid, status=2),
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/jobs/{jid}",
            json=payloads.job(id=jid, status=2),
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/jobs/{jid}",
            json=payloads.job(id=jid, status=3),  # SUCCEEDED
        )

        j = Job(**payloads.job(id=jid, status=2))
        session._bind(j)
        j.wait(poll_interval=0)
        assert j.status == JobStatus.SUCCEEDED

    def test_wait_times_out(self, httpx_mock, session, payloads):
        import pytest

        jid = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/jobs/{jid}",
            json=payloads.job(id=jid, status=2),
            is_reusable=True,
        )
        j = Job(**payloads.job(id=jid, status=2))
        session._bind(j)
        with pytest.raises(TimeoutError):
            j.wait(timeout=0.001, poll_interval=0)

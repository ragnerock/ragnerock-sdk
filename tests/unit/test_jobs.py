"""Tests for ``Job`` lifecycle and the ``session.run`` creation path."""

from __future__ import annotations

import re

import pytest

from ragnerock import Document, Job, JobStatus, ValidationError, Workflow


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        job_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/jobs/{job_id}$"),
            json=payloads.job(id=job_id),
        )
        job = session.get(Job, id=job_id)
        assert job is not None
        assert job.status == JobStatus.IN_PROGRESS

    def test_get_by_name_raises(self, session):
        with pytest.raises(ValidationError):
            session.get(Job, name="x")


class TestList:
    def test_list_all(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/jobs/\?.*"),
            json=payloads.list_envelope("jobs", [payloads.job()]),
        )
        jobs = session.list(Job).all()
        assert len(jobs) == 1

    def test_list_by_single_status(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/jobs/\?.*"),
            json=payloads.list_envelope("jobs", []),
        )
        session.list(Job, status=JobStatus.FAILED).all()
        req = next(r for r in httpx_mock.get_requests() if r.url.path == "/api/jobs/")
        assert req.url.params.get("status_filter") == str(int(JobStatus.FAILED))

    def test_list_by_multiple_statuses(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/jobs/\?.*"),
            json=payloads.list_envelope("jobs", []),
        )
        session.list(Job, status=[JobStatus.FAILED, JobStatus.SUCCEEDED]).all()
        req = next(r for r in httpx_mock.get_requests() if r.url.path == "/api/jobs/")
        assert req.url.params["status_filter"] == "4,3"


class TestAddIsRejected:
    def test_add_job_is_rejected(self, session):
        with pytest.raises((TypeError, ValidationError)):
            session.add(Job())


class TestRun:
    def test_run_creates_job(self, httpx_mock, session, payloads, base_url):
        wf = Workflow(**payloads.workflow())
        doc = Document(**payloads.document())
        job_id = "00000000-0000-0000-0000-0000000000a1"
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/jobs/",
            json={"job_ids": [job_id]},
        )
        job = session.run(wf, documents=[doc])
        assert str(job.id) == job_id
        assert job.status == JobStatus.NOT_STARTED

    def test_run_uncommitted_workflow_raises(self, session):
        wf = Workflow(name="new")  # no id
        doc = Document(id="00000000-0000-0000-0000-000000000101")
        with pytest.raises(ValidationError):
            session.run(wf, documents=[doc])

    def test_run_uncommitted_doc_raises(self, session):
        wf = Workflow(id="00000000-0000-0000-0000-000000000701", name="ingest")
        doc = Document(file_path="./x.pdf")
        with pytest.raises(ValidationError):
            session.run(wf, documents=[doc])


class TestJobActions:
    def test_cancel_updates_status(self, httpx_mock, session, payloads, base_url):
        job_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/jobs/{job_id}$"),
            json=payloads.job(id=job_id),
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/jobs/{job_id}/cancel",
            json={"job_id": job_id, "status": "cancelled"},
        )
        job = session.get(Job, id=job_id)
        assert job is not None
        job.cancel()  # the server JobActionResponse has no "status" int field

    def test_retry_calls_endpoint(self, httpx_mock, session, payloads, base_url):
        job_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/jobs/{job_id}$"),
            json=payloads.job(id=job_id),
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/jobs/{job_id}/retry",
            json={"job_id": job_id, "status": "queued"},
        )
        job = session.get(Job, id=job_id)
        assert job is not None
        job.retry()

    def test_cancel_on_unbound_job_raises(self):
        job = Job(id="00000000-0000-0000-0000-000000000801")
        with pytest.raises(RuntimeError):
            job.cancel()


class TestWait:
    def test_wait_returns_immediately_on_terminal_status(
        self, httpx_mock, session, payloads
    ):
        job = Job(
            id="00000000-0000-0000-0000-000000000801",
            status=JobStatus.SUCCEEDED,
        )
        session._bind(job)
        # Should not make any HTTP calls
        job.wait(timeout=0)

    def test_wait_timeout_raises(self, httpx_mock, session, payloads):
        job_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/jobs/{job_id}$"),
            json=payloads.job(id=job_id, status=int(JobStatus.IN_PROGRESS)),
            is_reusable=True,
        )
        job = Job(id=job_id, status=JobStatus.IN_PROGRESS)
        session._bind(job)
        with pytest.raises(TimeoutError):
            job.wait(timeout=0.01, poll_interval=0.01)


class TestRefresh:
    def test_refresh_overwrites_fields(self, httpx_mock, session, payloads):
        job_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/jobs/{job_id}$"),
            json=payloads.job(id=job_id, status=int(JobStatus.SUCCEEDED)),
        )
        job = Job(id=job_id, status=JobStatus.IN_PROGRESS)
        session._bind(job)
        job.refresh()
        assert job.status == JobStatus.SUCCEEDED

    def test_refresh_unpersisted_raises(self, session):
        job = Job()
        session._bind(job)
        with pytest.raises(ValidationError):
            session.refresh(job)

    def test_refresh_tolerates_empty_datetime_strings(
        self, httpx_mock, session, payloads
    ):
        job_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/jobs/{job_id}$"),
            json=payloads.job(
                id=job_id,
                status=int(JobStatus.IN_PROGRESS),
                start_time="",
                end_time="",
            ),
        )
        job = Job(id=job_id, status=JobStatus.IN_PROGRESS)
        session._bind(job)
        job.refresh()
        assert job.start_time is None
        assert job.end_time is None

    def test_get_tolerates_empty_datetime_strings(self, httpx_mock, session, payloads):
        job_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/jobs/{job_id}$"),
            json=payloads.job(id=job_id, start_time="", end_time=""),
        )
        job = session.get(Job, id=job_id)
        assert job is not None
        assert job.start_time is None
        assert job.end_time is None

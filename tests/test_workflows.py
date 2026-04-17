"""Tests for Workflow CRUD and running via session.run()."""

from __future__ import annotations

import re
from uuid import UUID

from ragnerock import Document, Job, Workflow
from tests.conftest import TEST_HOST


class TestList:
    def test_list_workflows(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/workflows/\?.*"),
            json=payloads.list_envelope("workflows", [payloads.workflow()]),
        )
        wfs = session.list(Workflow).all()
        assert len(wfs) == 1
        assert wfs[0].name == "ingest"


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        wid = "00000000-0000-0000-0000-000000000701"
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_HOST}/api/workflows/{wid}",
            json=payloads.workflow(id=wid),
        )
        wf = session.get(Workflow, id=wid)
        assert wf is not None
        assert wf.id == UUID(wid)

    def test_get_by_name_via_list(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/workflows/\?.*"),
            json=payloads.list_envelope(
                "workflows",
                [payloads.workflow(name="ingest"), payloads.workflow(id="00000000-0000-0000-0000-000000000702", name="other")],
            ),
            is_reusable=True,
        )
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/workflows/[0-9a-f-]+$"),
            json=payloads.workflow(name="ingest"),
            is_reusable=True,
        )
        wf = session.get(Workflow, name="ingest")
        assert wf is not None
        assert wf.name == "ingest"


class TestCreate:
    def test_add_commit_posts_workflow(self, httpx_mock, session, payloads):
        new_id = "00000000-0000-0000-0000-000000000710"
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/workflows/",
            json=payloads.workflow(id=new_id, name="new"),
        )
        wf = Workflow(name="new", description="x")
        session.add(wf)
        session.commit()
        assert wf.id == UUID(new_id)


class TestUpdate:
    def test_update_renames(self, httpx_mock, session, payloads):
        wid = "00000000-0000-0000-0000-000000000701"
        httpx_mock.add_response(
            method="PUT",
            url=f"{TEST_HOST}/api/workflows/{wid}",
            json=payloads.workflow(id=wid, name="renamed"),
        )
        wf = Workflow(**payloads.workflow(id=wid))
        wf.name = "renamed"
        session.update(wf)
        session.commit()
        assert wf.name == "renamed"


class TestDelete:
    def test_delete_removes(self, httpx_mock, session, payloads):
        wid = "00000000-0000-0000-0000-000000000701"
        httpx_mock.add_response(
            method="DELETE",
            url=f"{TEST_HOST}/api/workflows/{wid}",
            json={},
        )
        wf = Workflow(**payloads.workflow(id=wid))
        session.delete(wf)
        session.commit()


class TestRun:
    def test_run_creates_manual_jobs(self, httpx_mock, session, payloads):
        wid = "00000000-0000-0000-0000-000000000701"
        doc_id = "00000000-0000-0000-0000-000000000101"
        job_id = "00000000-0000-0000-0000-000000000801"

        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_HOST}/api/jobs/",
            json={"job_ids": [job_id]},
        )

        wf = Workflow(**payloads.workflow(id=wid))
        doc = Document(**payloads.document(id=doc_id))
        session._bind(wf)
        session._bind(doc)

        job = session.run(wf, documents=[doc])
        assert isinstance(job, Job)
        assert job.id == UUID(job_id)

        # Body must carry document_ids + workflow_ids.
        req = next(
            r
            for r in httpx_mock.get_requests()
            if r.method == "POST" and r.url.path == "/api/jobs/"
        )
        body = req.read()
        assert doc_id.encode() in body
        assert wid.encode() in body

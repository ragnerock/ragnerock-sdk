"""Tests for ``Run`` lifecycle and the ``session.run`` creation path."""

from __future__ import annotations

import json
import re

import pytest

from ragnerock import Agent, Document, Run, RunKind, RunStatus, ValidationError


class TestGet:
    def test_get_by_id(self, httpx_mock, session, payloads):
        run_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/runs/{run_id}$"),
            json=payloads.run(id=run_id),
        )
        run = session.get(Run, id=run_id)
        assert run is not None
        assert run.status == RunStatus.IN_PROGRESS

    def test_get_parses_kind_and_agent_ids(self, httpx_mock, session, payloads):
        run_id = "00000000-0000-0000-0000-000000000801"
        agent_id = "00000000-0000-0000-0000-000000000701"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/runs/{run_id}$"),
            json=payloads.run(id=run_id, kind=1, agent_ids=[agent_id]),
        )
        run = session.get(Run, id=run_id)
        assert run is not None
        assert run.kind is RunKind.AUTOMATIC
        assert [str(a) for a in run.agent_ids] == [agent_id]

    def test_get_by_name_raises(self, session):
        with pytest.raises(ValidationError):
            session.get(Run, name="x")


class TestList:
    def test_list_all(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/runs/\?.*"),
            json=payloads.list_envelope("runs", [payloads.run()]),
        )
        runs = session.list(Run).all()
        assert len(runs) == 1

    def test_list_by_single_status(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/runs/\?.*"),
            json=payloads.list_envelope("runs", []),
        )
        session.list(Run, status=RunStatus.FAILED).all()
        req = next(r for r in httpx_mock.get_requests() if r.url.path == "/api/runs/")
        assert req.url.params.get("status_filter") == str(int(RunStatus.FAILED))

    def test_list_by_multiple_statuses(self, httpx_mock, session, payloads):
        httpx_mock.add_response(
            method="GET",
            url=re.compile(r".*/api/runs/\?.*"),
            json=payloads.list_envelope("runs", []),
        )
        session.list(Run, status=[RunStatus.FAILED, RunStatus.SUCCEEDED]).all()
        req = next(r for r in httpx_mock.get_requests() if r.url.path == "/api/runs/")
        assert req.url.params["status_filter"] == "4,3"


class TestAddIsRejected:
    def test_add_run_is_rejected(self, session):
        with pytest.raises(ValidationError, match=r"session\.run\(agent"):
            session.add(Run())


class TestRun:
    def test_run_creates_run(self, httpx_mock, session, payloads, base_url):
        agent = Agent(**payloads.agent())
        doc = Document(**payloads.document())
        run_id = "00000000-0000-0000-0000-0000000000a1"
        provenance_id = "00000000-0000-0000-0000-0000000000b1"
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/runs/",
            json={"run_ids": [run_id], "provenance_ids": [provenance_id]},
        )
        run = session.run(agent, documents=[doc])
        assert str(run.id) == run_id
        assert run.status == RunStatus.NOT_STARTED
        assert run._is_bound
        body = json.loads(httpx_mock.get_requests()[-1].content)
        assert body["agent_ids"] == [str(agent.id)]
        assert body["document_ids"] == [str(doc.id)]

    def test_run_uncommitted_agent_raises(self, session):
        agent = Agent(name="new")  # no id
        doc = Document(id="00000000-0000-0000-0000-000000000101")
        with pytest.raises(ValidationError):
            session.run(agent, documents=[doc])

    def test_run_uncommitted_doc_raises(self, session):
        agent = Agent(id="00000000-0000-0000-0000-000000000701", name="ingest")
        doc = Document(file_path="./x.pdf")
        with pytest.raises(ValidationError):
            session.run(agent, documents=[doc])


class TestRunActions:
    def test_cancel_refreshes_status(self, httpx_mock, session, payloads, base_url):
        run_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/runs/{run_id}$"),
            json=payloads.run(id=run_id, status=2),
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/runs/{run_id}/cancel",
            json={"run_id": run_id, "status": "cancelled"},
        )
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/runs/{run_id}$"),
            json=payloads.run(id=run_id, status=4, status_message="Cancelled"),
        )
        run = session.get(Run, id=run_id)
        assert run is not None
        run.cancel()
        assert run.status == RunStatus.FAILED
        assert run.status_message == "Cancelled"

    def test_retry_refreshes_status(self, httpx_mock, session, payloads, base_url):
        run_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/runs/{run_id}$"),
            json=payloads.run(id=run_id, status=4),
        )
        httpx_mock.add_response(
            method="POST",
            url=f"{base_url}/api/runs/{run_id}/retry",
            json={"run_id": run_id, "status": "retrying"},
        )
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/runs/{run_id}$"),
            json=payloads.run(id=run_id, status=1),
        )
        run = session.get(Run, id=run_id)
        assert run is not None
        run.retry()
        assert run.status == RunStatus.NOT_STARTED

    def test_cancel_on_unbound_run_raises(self):
        run = Run(id="00000000-0000-0000-0000-000000000801")
        with pytest.raises(RuntimeError):
            run.cancel()


class TestWait:
    def test_wait_returns_immediately_on_terminal_status(
        self, httpx_mock, session, payloads
    ):
        run = Run(
            id="00000000-0000-0000-0000-000000000801",
            status=RunStatus.SUCCEEDED,
        )
        session._bind(run)
        # Should not make any HTTP calls
        run.wait(timeout=0)

    def test_wait_timeout_raises(self, httpx_mock, session, payloads):
        run_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/runs/{run_id}$"),
            json=payloads.run(id=run_id, status=int(RunStatus.IN_PROGRESS)),
            is_reusable=True,
        )
        run = Run(id=run_id, status=RunStatus.IN_PROGRESS)
        session._bind(run)
        with pytest.raises(TimeoutError):
            run.wait(timeout=0.01, poll_interval=0.01)


class TestRefresh:
    def test_refresh_overwrites_fields(self, httpx_mock, session, payloads):
        run_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/runs/{run_id}$"),
            json=payloads.run(id=run_id, status=int(RunStatus.SUCCEEDED)),
        )
        run = Run(id=run_id, status=RunStatus.IN_PROGRESS)
        session._bind(run)
        run.refresh()
        assert run.status == RunStatus.SUCCEEDED

    def test_refresh_unpersisted_raises(self, session):
        run = Run()
        session._bind(run)
        with pytest.raises(ValidationError):
            session.refresh(run)

    def test_refresh_tolerates_empty_datetime_strings(
        self, httpx_mock, session, payloads
    ):
        run_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/runs/{run_id}$"),
            json=payloads.run(
                id=run_id,
                status=int(RunStatus.IN_PROGRESS),
                start_time="",
                end_time="",
            ),
        )
        run = Run(id=run_id, status=RunStatus.IN_PROGRESS)
        session._bind(run)
        run.refresh()
        assert run.start_time is None
        assert run.end_time is None

    def test_get_tolerates_empty_datetime_strings(self, httpx_mock, session, payloads):
        run_id = "00000000-0000-0000-0000-000000000801"
        httpx_mock.add_response(
            method="GET",
            url=re.compile(rf".*/api/runs/{run_id}$"),
            json=payloads.run(id=run_id, start_time="", end_time=""),
        )
        run = session.get(Run, id=run_id)
        assert run is not None
        assert run.start_time is None
        assert run.end_time is None
